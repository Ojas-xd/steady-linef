from __future__ import annotations

import base64
import gc
import io
import logging
import random
import threading
from datetime import datetime, timedelta

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import CrowdCount
from app.schemas import CrowdAnalyzeOut

router = APIRouter(prefix="/crowd", tags=["Crowd"])
logger = logging.getLogger(__name__)

# Lazy-load Ultralytics YOLO only when YOLO_MODE=ultralytics
_model = None
_model_error: str | None = None
_model_lock = threading.Lock()
_warm_started = False
_warm_lock = threading.Lock()

_predict_lock = threading.Lock()

_YOLO_IMGSZ = 320
_MAX_INPUT_SIDE = 960


def _downscale_bgr(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    m = max(h, w)
    if m <= _MAX_INPUT_SIDE:
        return img
    scale = _MAX_INPUT_SIDE / m
    nw, nh = int(w * scale), int(h * scale)
    return cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)


def start_background_yolo_warm() -> None:
    """Warm real YOLO only when configured; hog/demo skip PyTorch entirely."""
    if settings.YOLO_MODE != "ultralytics":
        return
    _schedule_background_warm()


def _schedule_background_warm() -> None:
    global _warm_started
    with _warm_lock:
        if _warm_started or _model is not None or _model_error is not None:
            return
        _warm_started = True

    def _worker() -> None:
        try:
            _get_model()
        except Exception as e:
            logger.warning(f"[YOLO] Background warm thread exit: {e}")

    threading.Thread(target=_worker, name="yolo-warm", daemon=True).start()


def _get_model():
    global _model, _model_error
    if _model is not None:
        return _model
    if _model_error is not None:
        raise HTTPException(status_code=503, detail=f"YOLO model not available: {_model_error}")

    with _model_lock:
        if _model is not None:
            return _model
        if _model_error is not None:
            raise HTTPException(status_code=503, detail=f"YOLO model not available: {_model_error}")
        try:
            from ultralytics import YOLO
            import os

            logger.info(f"[YOLO] Loading model from: {settings.YOLO_MODEL_PATH}")
            logger.info(f"[YOLO] Current working directory: {os.getcwd()}")
            logger.info(f"[YOLO] Model file exists: {os.path.exists(settings.YOLO_MODEL_PATH)}")

            if not os.path.exists(settings.YOLO_MODEL_PATH):
                logger.warning(
                    f"[YOLO] Model file not found at {settings.YOLO_MODEL_PATH}, will attempt download..."
                )

            try:
                _model_local = YOLO(settings.YOLO_MODEL_PATH)
                logger.info(
                    f"[YOLO] Model loaded. Classes: {len(_model_local.names)}, "
                    f"Names: {list(_model_local.names.values())[:5]}..."
                )
            except Exception as load_err:
                logger.error(f"[YOLO] Model load failed: {load_err}")
                raise

            try:
                import torch

                torch.set_num_threads(1)
                dummy = np.zeros((320, 320, 3), dtype=np.uint8)
                logger.info("[YOLO] Running warmup inference...")
                with _predict_lock:
                    with torch.inference_mode():
                        _model_local.predict(
                            dummy,
                            verbose=False,
                            conf=0.25,
                            device="cpu",
                            imgsz=_YOLO_IMGSZ,
                        )
                del dummy
                logger.info("[YOLO] Warmup complete. Model ready!")
            except Exception as warmup_err:
                logger.error(f"[YOLO] Warmup failed: {warmup_err}")
                raise

            _model = _model_local

        except Exception as e:
            import traceback

            _model_error = str(e)
            logger.error(f"[YOLO] Failed to load model: {e}")
            logger.error(f"[YOLO] Traceback: {traceback.format_exc()}")

    if _model_error:
        raise HTTPException(status_code=503, detail=f"YOLO model not available: {_model_error}")
    return _model


def _hog_people_detect(img_bgr: np.ndarray) -> tuple[int, list[dict[str, object]], np.ndarray]:
    """OpenCV HOG pedestrian detector — CPU only, no PyTorch; good enough for demos on small hosts."""
    out = img_bgr.copy()
    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
    rects, weights = hog.detectMultiScale(out, winStride=(8, 8), padding=(8, 8), scale=1.05)
    detections: list[dict[str, object]] = []
    for i, (x, y, w, h) in enumerate(rects):
        x1, y1, x2, y2 = int(x), int(y), int(x + w), int(y + h)
        raw_w = float(weights[i][0]) if len(weights) > i and len(weights[i]) > 0 else 0.5
        conf = float(min(0.99, max(0.25, abs(raw_w) / 3.0)))
        detections.append({"box": [x1, y1, x2, y2], "confidence": round(conf, 2)})
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = f"Person {conf:.2f}"
        label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
        cv2.rectangle(
            out,
            (x1, y1 - label_size[1] - 10),
            (x1 + label_size[0], y1),
            (0, 255, 0),
            -1,
        )
        cv2.putText(out, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
    return len(detections), detections, out


def _demo_detect(img_bgr: np.ndarray) -> tuple[int, list[dict[str, object]], np.ndarray]:
    """Placeholder boxes — always succeeds (for worst-case hosting)."""
    out = img_bgr.copy()
    h, w = out.shape[:2]
    n = random.randint(0, min(3, max(1, w // 120)))
    detections: list[dict[str, object]] = []
    for _ in range(n):
        bw, bh = max(40, w // 6), max(80, h // 4)
        x1 = random.randint(0, max(0, w - bw))
        y1 = random.randint(0, max(0, h - bh))
        x2, y2 = x1 + bw, y1 + bh
        conf = round(random.uniform(0.35, 0.85), 2)
        detections.append({"box": [x1, y1, x2, y2], "confidence": conf})
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.putText(
        out,
        "YOLO demo",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 200, 255),
        2,
    )
    return len(detections), detections, out


def _run_ultralytics(frame_bgr: np.ndarray) -> tuple[int, list[dict[str, object]], np.ndarray]:
    import torch

    model = _get_model()
    out = frame_bgr.copy()
    results = None
    try:
        with _predict_lock:
            with torch.inference_mode():
                results = model.predict(
                    out,
                    verbose=False,
                    conf=0.25,
                    iou=0.45,
                    classes=[0],
                    device="cpu",
                    imgsz=_YOLO_IMGSZ,
                )
        count = 0
        detections: list[dict[str, object]] = []
        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                if cls_id == 0 and conf >= 0.25:
                    count += 1
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    detections.append({"box": [x1, y1, x2, y2], "confidence": round(conf, 2)})
                    cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    label = f"Person {conf:.2f}"
                    label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
                    cv2.rectangle(
                        out,
                        (x1, y1 - label_size[1] - 10),
                        (x1 + label_size[0], y1),
                        (0, 255, 0),
                        -1,
                    )
                    cv2.putText(out, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
        return count, detections, out
    finally:
        if results is not None:
            del results
        gc.collect(0)


def _parse_roi_optional_strings(
    roi_x: str | None, roi_y: str | None, roi_w: str | None, roi_h: str | None
) -> tuple[float, float, float, float] | None:
    def _empty(v: str | None) -> bool:
        return v is None or (isinstance(v, str) and not str(v).strip())

    if all(_empty(v) for v in (roi_x, roi_y, roi_w, roi_h)):
        return None
    if any(_empty(v) for v in (roi_x, roi_y, roi_w, roi_h)):
        raise HTTPException(
            status_code=400,
            detail="Queue zone requires all four fields: roi_x, roi_y, roi_w, roi_h (0-1 normalized to image).",
        )
    try:
        rx, ry, rw, rh = float(str(roi_x).strip()), float(str(roi_y).strip()), float(str(roi_w).strip()), float(str(roi_h).strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="ROI values must be numbers") from None
    if rw <= 0 or rh <= 0:
        raise HTTPException(status_code=400, detail="roi_w and roi_h must be positive")
    if rx < 0 or ry < 0 or rx >= 1 or ry >= 1:
        raise HTTPException(status_code=400, detail="roi_x and roi_y must be in [0, 1)")
    if rx + rw > 1.001 or ry + rh > 1.001:
        raise HTTPException(status_code=400, detail="ROI must fit inside the image")
    return (rx, ry, min(rw, 1.0 - rx), min(rh, 1.0 - ry))


def _apply_queue_zone(
    drawn_bgr: np.ndarray,
    detections: list[dict[str, object]],
    roi: tuple[float, float, float, float],
) -> tuple[np.ndarray, list[dict[str, object]], int]:
    """Keep detections whose box center lies inside normalized ROI; draw yellow queue rectangle."""
    h, w = drawn_bgr.shape[:2]
    rx, ry, rw, rh = roi
    x1 = int(rx * w)
    y1 = int(ry * h)
    x2 = int((rx + rw) * w)
    y2 = int((ry + rh) * h)
    x2 = max(x1 + 2, min(w, x2))
    y2 = max(y1 + 2, min(h, y2))

    filtered: list[dict[str, object]] = []
    for d in detections:
        box = d.get("box")
        if not (isinstance(box, list) and len(box) >= 4):
            continue
        bx1, by1, bx2, by2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
        cx = 0.5 * (bx1 + bx2)
        cy = 0.5 * (by1 + by2)
        if x1 <= cx <= x2 and y1 <= cy <= y2:
            filtered.append(d)

    vis = drawn_bgr.copy()
    cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 255), 2)
    cv2.putText(
        vis,
        "Queue zone",
        (x1, max(20, y1 - 6)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (0, 255, 255),
        2,
    )
    cv2.putText(
        vis,
        f"In zone: {len(filtered)}",
        (10, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 255, 255),
        2,
    )
    return vis, filtered, len(filtered)


def _finalize_analyze(
    frame_bgr_drawn: np.ndarray, count: int, detections: list, db: Session, *, queue_zone_applied: bool
) -> dict:
    frame_rgb = cv2.cvtColor(frame_bgr_drawn, cv2.COLOR_BGR2RGB)
    annotated_image = Image.fromarray(frame_rgb)
    buffered = io.BytesIO()
    annotated_image.save(buffered, format="JPEG", quality=85)
    img_base64 = base64.b64encode(buffered.getvalue()).decode()

    record = CrowdCount(count=count, timestamp=datetime.utcnow())
    db.add(record)
    db.commit()

    return {
        "count": count,
        "image": f"data:image/jpeg;base64,{img_base64}",
        "detections": detections,
        "queue_zone_applied": queue_zone_applied,
    }


@router.get("/health")
def crowd_health_check():
    mode = settings.YOLO_MODE
    if mode == "demo":
        return {
            "status": "healthy",
            "model_loaded": True,
            "model_classes": ["person"],
            "inference_backend": "demo",
        }
    if mode == "hog":
        return {
            "status": "healthy",
            "model_loaded": True,
            "model_classes": ["person"],
            "inference_backend": "opencv_hog",
        }
    if mode == "replicate":
        has_token = bool((settings.REPLICATE_API_TOKEN or "").strip())
        return {
            "status": "healthy",
            "model_loaded": True,
            "model_classes": ["person"],
            "inference_backend": "replicate" if has_token else "opencv_hog_fallback",
            "message": (
                None
                if has_token
                else "Add REPLICATE_API_TOKEN on Render for hosted YOLOv8; until then analyze uses HOG."
            ),
        }

    # ultralytics
    if _model_error:
        return {
            "status": "unhealthy",
            "model_loaded": False,
            "error": _model_error,
            "inference_backend": "ultralytics",
        }
    if _model is not None:
        m = _model
        return {
            "status": "healthy",
            "model_loaded": True,
            "model_classes": list(m.names.values()) if hasattr(m, "names") else [],
            "inference_backend": "ultralytics",
        }
    _schedule_background_warm()
    return {
        "status": "pending",
        "model_loaded": False,
        "message": "Model loading in background; wait ~1–2 min on first deploy then retry.",
        "inference_backend": "ultralytics",
    }


@router.get("/count")
def get_live_count(db: Session = Depends(get_db)):
    cutoff = datetime.utcnow() - timedelta(minutes=5)

    latest = (
        db.query(CrowdCount)
        .filter(CrowdCount.timestamp >= cutoff)
        .order_by(CrowdCount.timestamp.desc())
        .first()
    )

    return {
        "count": latest.count if latest else 0,
        "timestamp": latest.timestamp.isoformat() if latest else datetime.utcnow().isoformat(),
    }


@router.post("/analyze", response_model=CrowdAnalyzeOut)
async def analyze_frame(
    file: UploadFile = File(...),
    roi_x: str | None = Form(default=None),
    roi_y: str | None = Form(default=None),
    roi_w: str | None = Form(default=None),
    roi_h: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    logger.info(
        f"[YOLO] Analyze mode={settings.YOLO_MODE} file={file.filename} content_type={file.content_type}"
    )

    roi_norm: tuple[float, float, float, float] | None = None
    try:
        roi_norm = _parse_roi_optional_strings(roi_x, roi_y, roi_w, roi_h)
    except HTTPException:
        raise

    try:
        contents = await file.read()
        if not contents:
            raise HTTPException(status_code=400, detail="Empty file uploaded")

        logger.info(f"[YOLO] File received: {len(contents)} bytes")

        image = Image.open(io.BytesIO(contents))

        if image.mode != "RGB":
            image = image.convert("RGB")

        frame = np.array(image)

        if len(frame.shape) != 3 or frame.shape[2] != 3:
            raise HTTPException(status_code=400, detail=f"Invalid image dimensions: {frame.shape}")

        logger.info(f"Processing image: shape={frame.shape}, size={len(contents)} bytes")

        image.close()
        del contents

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process uploaded image: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid image file: {str(e)}")

    if len(frame.shape) == 3 and frame.shape[2] == 3:
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    else:
        frame_bgr = frame
    del frame

    infer_bgr = _downscale_bgr(frame_bgr)
    if infer_bgr.shape != frame_bgr.shape:
        del frame_bgr
    frame_bgr = infer_bgr

    mode = settings.YOLO_MODE
    try:
        if mode == "demo":
            count, detections, drawn = _demo_detect(frame_bgr)
        elif mode == "hog":
            count, detections, drawn = _hog_people_detect(frame_bgr)
        elif mode == "replicate":
            tok = (settings.REPLICATE_API_TOKEN or "").strip()
            if not tok:
                logger.warning("[YOLO] replicate mode but REPLICATE_API_TOKEN empty — using HOG")
                count, detections, drawn = _hog_people_detect(frame_bgr)
            else:
                from app.replicate_yolo import run_replicate_yolov8

                try:
                    count, detections, drawn = run_replicate_yolov8(frame_bgr, tok)
                except Exception as rep_e:
                    logger.warning("[YOLO] Replicate call failed, using HOG: %s", rep_e)
                    count, detections, drawn = _hog_people_detect(frame_bgr)
        else:
            count, detections, drawn = _run_ultralytics(frame_bgr)
        del frame_bgr
        logger.info(f"[YOLO] {mode} complete: count={count}")
        if roi_norm is not None:
            drawn, detections, count = _apply_queue_zone(drawn, detections, roi_norm)
        return _finalize_analyze(
            drawn, count, detections, db, queue_zone_applied=roi_norm is not None
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[YOLO] analyze failed ({mode}): {e}")
        import traceback

        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"YOLO analysis failed: {str(e)}")
    finally:
        gc.collect(0)

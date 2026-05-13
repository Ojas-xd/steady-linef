from __future__ import annotations

import base64
import gc
import io
import logging
import threading
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from PIL import Image
import numpy as np
import cv2

from app.database import get_db
from app.models import CrowdCount
from app.schemas import CrowdAnalyzeOut

router = APIRouter(prefix="/crowd", tags=["Crowd"])
logger = logging.getLogger(__name__)

# Lazy-load YOLO (single-flight: parallel /health + /analyze used to double-download and OOM Render)
_model = None
_model_error: str | None = None
_model_lock = threading.Lock()
_warm_started = False
_warm_lock = threading.Lock()

# Only one predict() at a time — overlapping Ultralytics runs spike RAM on small hosts
_predict_lock = threading.Lock()

# Smaller imgsz keeps CPU/RAM lower on Render free/small instances
_YOLO_IMGSZ = 320
# Downscale huge camera frames before inference
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
    """Call once at app startup so the model loads off the hot request path."""
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
            from app.config import settings
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


@router.get("/health")
def crowd_health_check():
    """Fast status only — never blocks on model download (that was killing the worker + CORS)."""
    if _model_error:
        return {
            "status": "unhealthy",
            "model_loaded": False,
            "error": _model_error,
        }
    if _model is not None:
        m = _model
        return {
            "status": "healthy",
            "model_loaded": True,
            "model_classes": list(m.names.values()) if hasattr(m, "names") else [],
        }
    _schedule_background_warm()
    return {
        "status": "pending",
        "model_loaded": False,
        "message": "Model loading in background; wait ~1–2 min on first deploy then retry health or analyze.",
    }


@router.get("/count")
def get_live_count(db: Session = Depends(get_db)):
    """Get latest crowd count, but only if it's recent (within last 5 minutes)"""
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
async def analyze_frame(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload an image frame → YOLO detects people → returns count + annotated image."""
    logger.info(f"[YOLO] Analyze request received: filename={file.filename}, content_type={file.content_type}")

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

    results = None
    try:
        import torch

        model = _get_model()
        logger.info(f"Running YOLO inference on frame shape: {frame_bgr.shape} (BGR)")
        with _predict_lock:
            with torch.inference_mode():
                results = model.predict(
                    frame_bgr,
                    verbose=False,
                    conf=0.25,
                    iou=0.45,
                    classes=[0],
                    device="cpu",
                    imgsz=_YOLO_IMGSZ,
                )
        logger.info(f"YOLO inference completed, processing {len(results)} result(s)")

        count = 0
        detections = []

        for r in results:
            logger.debug(f"Result boxes: {len(r.boxes)}")
            for box in r.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])

                if cls_id == 0 and conf >= 0.25:
                    count += 1
                    x1, y1, x2, y2 = map(int, box.xyxy[0])

                    detections.append(
                        {
                            "box": [x1, y1, x2, y2],
                            "confidence": round(conf, 2),
                        }
                    )

                    cv2.rectangle(frame_bgr, (x1, y1), (x2, y2), (0, 255, 0), 2)

                    label = f"Person {conf:.2f}"
                    label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
                    cv2.rectangle(
                        frame_bgr,
                        (x1, y1 - label_size[1] - 10),
                        (x1 + label_size[0], y1),
                        (0, 255, 0),
                        -1,
                    )
                    cv2.putText(frame_bgr, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)

        logger.info(f"Detection complete: {count} person(s) found with {len(detections)} detection record(s)")
        if count == 0:
            logger.info("No people detected in frame")

        frame_annotated = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        del frame_bgr

        annotated_image = Image.fromarray(frame_annotated)
        buffered = io.BytesIO()
        annotated_image.save(buffered, format="JPEG", quality=85)
        img_base64 = base64.b64encode(buffered.getvalue()).decode()
        del annotated_image
        del buffered
        del frame_annotated

        record = CrowdCount(count=count, timestamp=datetime.utcnow())
        db.add(record)
        db.commit()

        return {
            "count": count,
            "image": f"data:image/jpeg;base64,{img_base64}",
            "detections": detections,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"YOLO inference failed: {e}")
        import traceback

        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"YOLO analysis failed: {str(e)}")
    finally:
        if results is not None:
            del results
        gc.collect(0)

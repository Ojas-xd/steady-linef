"""
Queue / crowd camera pipeline (Ultralytics-style: detect people → optional queue ROI → count + viz).

Routers should stay thin; all detection, ROI, and drawing logic lives here with explicit edge-case handling.
"""
from __future__ import annotations

import base64
import gc
import io
import logging
import math
import random
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import cv2
import numpy as np
from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CrowdCount

logger = logging.getLogger(__name__)

Mode = Literal["hog", "ultralytics", "demo"]

# ── Tunables ───────────────────────────────────────────
MAX_UPLOAD_BYTES = 12 * 1024 * 1024  # avoid OOM on huge uploads
MIN_IMAGE_SIDE = 32
MAX_INPUT_SIDE = 960
YOLO_IMGSZ = 320
PERSON_CONF = 0.25
MIN_ROI_SIDE = 1e-4  # normalized; reject accidental lines
JPEG_QUALITY = 85


@dataclass(frozen=True, slots=True)
class PersonDetection:
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "box": [self.x1, self.y1, self.x2, self.y2],
            "confidence": round(self.confidence, 2),
        }


def _finite(x: float) -> bool:
    return math.isfinite(x)


def _clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def clamp_detection_to_frame(d: PersonDetection, w: int, h: int) -> PersonDetection | None:
    x1 = _clamp_int(d.x1, 0, w - 1)
    y1 = _clamp_int(d.y1, 0, h - 1)
    x2 = _clamp_int(d.x2, 0, w - 1)
    y2 = _clamp_int(d.y2, 0, h - 1)
    if x2 - x1 < 2 or y2 - y1 < 2:
        return None
    if x2 <= x1 or y2 <= y1:
        return None
    conf = d.confidence if _finite(d.confidence) else 0.25
    conf = float(min(0.99, max(0.01, conf)))
    return PersonDetection(x1=x1, y1=y1, x2=x2, y2=y2, confidence=conf)


def downscale_bgr(img: np.ndarray) -> np.ndarray:
    if img.ndim != 3 or img.shape[2] != 3:
        raise ValueError("Expected HxWx3 BGR image")
    hh, ww = img.shape[:2]
    m = max(hh, ww)
    if m <= MAX_INPUT_SIDE:
        return img
    scale = MAX_INPUT_SIDE / m
    nw, nh = max(1, int(ww * scale)), max(1, int(hh * scale))
    return cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)


def decode_upload_to_bgr(contents: bytes) -> np.ndarray:
    if not contents:
        raise ValueError("Empty file")
    if len(contents) > MAX_UPLOAD_BYTES:
        raise ValueError(f"Image too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)")
    try:
        im = Image.open(io.BytesIO(contents))
    except Exception as e:
        raise ValueError(f"Not a valid image: {e}") from e
    try:
        im = ImageOps.exif_transpose(im)
    except Exception:
        pass
    if im.mode != "RGB":
        im = im.convert("RGB")
    arr = np.asarray(im)
    im.close()
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError("Invalid decoded image shape")
    h, w = arr.shape[:2]
    if min(h, w) < MIN_IMAGE_SIDE:
        raise ValueError(f"Image too small (min side {MIN_IMAGE_SIDE}px)")
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def parse_roi_optional_strings(
    roi_x: str | None, roi_y: str | None, roi_w: str | None, roi_h: str | None
) -> tuple[float, float, float, float] | None:
    def _empty(v: str | None) -> bool:
        return v is None or (isinstance(v, str) and not str(v).strip())

    if all(_empty(v) for v in (roi_x, roi_y, roi_w, roi_h)):
        return None
    if any(_empty(v) for v in (roi_x, roi_y, roi_w, roi_h)):
        raise ValueError(
            "Queue zone requires all four fields: roi_x, roi_y, roi_w, roi_h (0–1 normalized to image)."
        )
    try:
        rx = float(str(roi_x).strip())
        ry = float(str(roi_y).strip())
        rw = float(str(roi_w).strip())
        rh = float(str(roi_h).strip())
    except ValueError as e:
        raise ValueError("ROI values must be finite numbers") from e
    if not all(_finite(v) for v in (rx, ry, rw, rh)):
        raise ValueError("ROI must be finite numbers (no NaN/Inf)")
    if rw < MIN_ROI_SIDE or rh < MIN_ROI_SIDE:
        raise ValueError("roi_w and roi_h too small")
    if rx < 0 or ry < 0 or rx >= 1 or ry >= 1:
        raise ValueError("roi_x and roi_y must be in [0, 1)")
    if rx + rw > 1.0001 or ry + rh > 1.0001:
        raise ValueError("ROI must fit inside the image")
    rw = min(rw, 1.0 - rx)
    rh = min(rh, 1.0 - ry)
    return (rx, ry, rw, rh)


def roi_norm_to_pixels(roi: tuple[float, float, float, float], w: int, h: int) -> tuple[int, int, int, int]:
    rx, ry, rw, rh = roi
    x1 = int(rx * w)
    y1 = int(ry * h)
    x2 = int((rx + rw) * w)
    y2 = int((ry + rh) * h)
    x1 = _clamp_int(x1, 0, max(0, w - 2))
    y1 = _clamp_int(y1, 0, max(0, h - 2))
    x2 = _clamp_int(x2, x1 + 2, w)
    y2 = _clamp_int(y2, y1 + 2, h)
    return x1, y1, x2, y2


def _center_in_roi(d: PersonDetection, rx1: int, ry1: int, rx2: int, ry2: int) -> bool:
    cx = 0.5 * (d.x1 + d.x2)
    cy = 0.5 * (d.y1 + d.y2)
    return rx1 <= cx <= rx2 and ry1 <= cy <= ry2


def _draw_label(img: np.ndarray, x1: int, y1: int, text: str, bgr: tuple[int, int, int]) -> None:
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
    ty = max(th + 6, y1)
    cv2.rectangle(img, (x1, ty - th - 6), (x1 + tw + 4, ty + 2), bgr, -1)
    cv2.putText(img, text, (x1 + 2, ty - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)


def render_queue_visual(
    base_bgr: np.ndarray,
    detections: list[PersonDetection],
    roi_norm: tuple[float, float, float, float] | None,
) -> tuple[np.ndarray, list[PersonDetection], int, int | None]:
    """
    Build annotated BGR frame (queue zone + person boxes).
    Returns (image, api_detections, api_count, total_in_frame_or_none).
    When ROI is set: API lists only in-zone; gray boxes for out-of-zone (video-style).
    """
    h, w = base_bgr.shape[:2]
    vis = base_bgr.copy()
    total = len(detections)

    if roi_norm is None:
        for d in detections:
            cv2.rectangle(vis, (d.x1, d.y1), (d.x2, d.y2), (0, 255, 0), 2)
            _draw_label(vis, d.x1, d.y1, f"{d.confidence:.2f}", (0, 180, 0))
        cv2.putText(
            vis,
            f"People: {total}",
            (10, 26),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2,
        )
        return vis, list(detections), total, None

    rx1, ry1, rx2, ry2 = roi_norm_to_pixels(roi_norm, w, h)
    in_zone: list[PersonDetection] = []
    out_zone: list[PersonDetection] = []
    for d in detections:
        if _center_in_roi(d, rx1, ry1, rx2, ry2):
            in_zone.append(d)
        else:
            out_zone.append(d)

    for d in out_zone:
        cv2.rectangle(vis, (d.x1, d.y1), (d.x2, d.y2), (80, 80, 80), 1)
    for d in in_zone:
        cv2.rectangle(vis, (d.x1, d.y1), (d.x2, d.y2), (0, 255, 0), 2)
        _draw_label(vis, d.x1, d.y1, f"{d.confidence:.2f}", (0, 140, 0))

    cv2.rectangle(vis, (rx1, ry1), (rx2, ry2), (0, 255, 255), 2)
    cv2.putText(vis, "Queue zone", (rx1, max(18, ry1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
    cv2.putText(
        vis,
        f"In zone: {len(in_zone)}  |  Full frame: {total}",
        (10, 26),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        (0, 255, 255),
        2,
    )
    return vis, in_zone, len(in_zone), total


# ── HOG ────────────────────────────────────────────────
def detect_hog(bgr: np.ndarray) -> list[PersonDetection]:
    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
    rects, weights = hog.detectMultiScale(bgr, winStride=(8, 8), padding=(8, 8), scale=1.05)
    hh, ww = bgr.shape[:2]
    out: list[PersonDetection] = []
    for i, (x, y, rw, rh) in enumerate(rects):
        x1, y1, x2, y2 = int(x), int(y), int(x + rw), int(y + rh)
        raw = 0.5
        if len(weights) > i and len(weights[i]) > 0:
            try:
                raw = float(weights[i][0])
            except (TypeError, ValueError, IndexError):
                raw = 0.5
        conf = float(min(0.99, max(PERSON_CONF, abs(raw) / 3.0)))
        d = clamp_detection_to_frame(PersonDetection(x1, y1, x2, y2, conf), ww, hh)
        if d:
            out.append(d)
    return out


# ── Demo ───────────────────────────────────────────────
def detect_demo(bgr: np.ndarray) -> list[PersonDetection]:
    hh, ww = bgr.shape[:2]
    n = random.randint(0, min(3, max(1, ww // 120)))
    out: list[PersonDetection] = []
    for _ in range(n):
        bw, bh = max(40, ww // 6), max(60, hh // 4)
        x1 = random.randint(0, max(0, ww - bw))
        y1 = random.randint(0, max(0, hh - bh))
        x2, y2 = x1 + bw, y1 + bh
        conf = round(random.uniform(0.35, 0.88), 2)
        d = clamp_detection_to_frame(PersonDetection(x1, y1, x2, y2, conf), ww, hh)
        if d:
            out.append(d)
    return out


# ── Ultralytics (lazy singleton) ───────────────────────
_model: Any = None
_model_error: str | None = None
_model_lock = threading.Lock()
_warm_started = False
_warm_lock = threading.Lock()
_predict_lock = threading.Lock()


def start_background_yolo_warm() -> None:
    if settings.YOLO_MODE != "ultralytics":
        return
    global _warm_started
    with _warm_lock:
        if _warm_started or _model is not None or _model_error is not None:
            return
        _warm_started = True

    def _worker() -> None:
        try:
            get_ultralytics_model()
        except Exception as e:
            logger.warning("[YOLO] background warm: %s", e)

    threading.Thread(target=_worker, name="yolo-warm", daemon=True).start()


def get_ultralytics_model() -> Any:
    global _model, _model_error
    if _model is not None:
        return _model
    if _model_error is not None:
        raise RuntimeError(_model_error)

    with _model_lock:
        if _model is not None:
            return _model
        if _model_error is not None:
            raise RuntimeError(_model_error)
        try:
            import os
            from ultralytics import YOLO

            path = settings.YOLO_MODEL_PATH
            logger.info("[YOLO] load path=%s exists=%s cwd=%s", path, os.path.exists(path), os.getcwd())
            m = YOLO(path)
            import torch

            torch.set_num_threads(1)
            dummy = np.zeros((320, 320, 3), dtype=np.uint8)
            with _predict_lock:
                with torch.inference_mode():
                    m.predict(dummy, verbose=False, conf=PERSON_CONF, device="cpu", imgsz=YOLO_IMGSZ)
            del dummy
            _model = m
            logger.info("[YOLO] ultralytics ready")
        except Exception as e:
            import traceback

            _model_error = str(e)
            logger.error("[YOLO] load failed: %s\n%s", e, traceback.format_exc())
            raise RuntimeError(_model_error) from e
    return _model


def detect_ultralytics(bgr: np.ndarray) -> list[PersonDetection]:
    import torch

    model = get_ultralytics_model()
    hh, ww = bgr.shape[:2]
    work = bgr.copy()
    results = None
    try:
        with _predict_lock:
            with torch.inference_mode():
                results = model.predict(
                    work,
                    verbose=False,
                    conf=PERSON_CONF,
                    iou=0.45,
                    classes=[0],
                    device="cpu",
                    imgsz=YOLO_IMGSZ,
                )
        out: list[PersonDetection] = []
        for r in results:
            if r.boxes is None or len(r.boxes) == 0:
                continue
            for box in r.boxes:
                try:
                    cls_id = int(box.cls[0].item())
                    conf = float(box.conf[0].item())
                except Exception:
                    continue
                if cls_id != 0 or conf < PERSON_CONF or not _finite(conf):
                    continue
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                d = clamp_detection_to_frame(PersonDetection(x1, y1, x2, y2, conf), ww, hh)
                if d:
                    out.append(d)
        return out
    finally:
        if results is not None:
            del results
        gc.collect(0)


def run_detection(mode: Mode, bgr: np.ndarray) -> list[PersonDetection]:
    if mode == "demo":
        return detect_demo(bgr)
    if mode == "hog":
        return detect_hog(bgr)
    return detect_ultralytics(bgr)


def health_payload() -> dict[str, Any]:
    mode = settings.YOLO_MODE
    if mode == "demo":
        return {"status": "healthy", "model_loaded": True, "model_classes": ["person"], "inference_backend": "demo"}
    if mode == "hog":
        return {"status": "healthy", "model_loaded": True, "model_classes": ["person"], "inference_backend": "opencv_hog"}
    if _model_error:
        return {
            "status": "unhealthy",
            "model_loaded": False,
            "error": _model_error,
            "inference_backend": "ultralytics",
        }
    if _model is not None:
        m = _model
        names = list(m.names.values()) if hasattr(m, "names") else []
        return {"status": "healthy", "model_loaded": True, "model_classes": names, "inference_backend": "ultralytics"}
    start_background_yolo_warm()
    return {
        "status": "pending",
        "model_loaded": False,
        "message": "Model loading in background; retry in ~1–2 min.",
        "inference_backend": "ultralytics",
    }


def encode_jpeg_data_uri(bgr: np.ndarray) -> str:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    im = Image.fromarray(rgb)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=JPEG_QUALITY)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def persist_crowd_count(db: Session, count: int) -> None:
    rec = CrowdCount(count=count, timestamp=datetime.utcnow())
    db.add(rec)
    db.commit()


def analyze_frame_pipeline(
    *,
    contents: bytes,
    roi_x: str | None,
    roi_y: str | None,
    roi_w: str | None,
    roi_h: str | None,
    db: Session,
) -> dict[str, Any]:
    """
    Full pipeline: bytes → BGR → downscale → detect → optional ROI → JPEG + DB.
    Raises ValueError for client errors, RuntimeError for model failures.
    """
    roi_norm = parse_roi_optional_strings(roi_x, roi_y, roi_w, roi_h)
    bgr = decode_upload_to_bgr(contents)
    bgr = downscale_bgr(bgr)

    mode: Mode
    m = settings.YOLO_MODE
    if m == "ultralytics":
        mode = "ultralytics"
    elif m == "demo":
        mode = "demo"
    else:
        mode = "hog"

    try:
        detections = run_detection(mode, bgr)
    except RuntimeError as e:
        raise RuntimeError(str(e)) from e

    vis, api_dets, api_count, total_frame = render_queue_visual(bgr, detections, roi_norm)
    data_uri = encode_jpeg_data_uri(vis)
    persist_crowd_count(db, api_count)

    return {
        "count": api_count,
        "image": data_uri,
        "detections": [d.to_api_dict() for d in api_dets],
        "queue_zone_applied": roi_norm is not None,
        "total_persons_frame": total_frame,
    }

"""
Queue / crowd camera pipeline using the robust YOLO manager.

This is a REFACTORED version using the new YOLO manager which provides:
- Auto-download of YOLOv8n model
- Automatic fallback to HOG if YOLO fails
- Better error handling and memory management
"""
from __future__ import annotations

import base64
import io
import logging
import random
from datetime import datetime
from typing import Any, Literal

import cv2
import numpy as np
from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CrowdCount
from app.services.yolo_manager import detect_people, get_detector_health, get_yolo_manager, PersonDetection

logger = logging.getLogger(__name__)

Mode = Literal["hog", "ultralytics", "demo"]

# ── Tunables ───────────────────────────────────────────
MAX_UPLOAD_BYTES = 12 * 1024 * 1024  # avoid OOM on huge uploads
MIN_IMAGE_SIDE = 32
MAX_INPUT_SIDE = 960
JPEG_QUALITY = 85


def _finite(x: float) -> bool:
    return __import__('math').isfinite(x)


def _clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


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
    MIN_ROI_SIDE = 1e-4
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


def detect_demo(bgr: np.ndarray) -> list[PersonDetection]:
    """Demo mode - generate fake detections for testing."""
    hh, ww = bgr.shape[:2]
    n = random.randint(0, min(3, max(1, ww // 120)))
    out: list[PersonDetection] = []
    for _ in range(n):
        bw, bh = max(40, ww // 6), max(60, hh // 4)
        x1 = random.randint(0, max(0, ww - bw))
        y1 = random.randint(0, max(0, hh - bh))
        x2, y2 = x1 + bw, y1 + bh
        conf = round(random.uniform(0.35, 0.88), 2)
        x1 = max(0, min(x1, ww - 1))
        y1 = max(0, min(y1, hh - 1))
        x2 = max(x1 + 2, min(x2, ww))
        y2 = max(y1 + 2, min(y2, hh))
        if x2 - x1 >= 2 and y2 - y1 >= 2:
            out.append(PersonDetection(x1, y1, x2, y2, conf))
    return out


def run_detection(mode: Mode, bgr: np.ndarray) -> list[PersonDetection]:
    """Run person detection with the specified mode."""
    if mode == "demo":
        return detect_demo(bgr)

    if mode == "hog":
        # Force HOG mode
        return detect_people(bgr, prefer_yolo=False)

    # Default: try YOLO first, fallback to HOG automatically
    return detect_people(bgr, prefer_yolo=True)


def health_payload() -> dict[str, Any]:
    """Get health status for the crowd detection endpoint."""
    mode = settings.YOLO_MODE
    health = get_detector_health()

    if mode == "demo":
        return {
            "status": "healthy",
            "model_loaded": True,
            "model_classes": ["person"],
            "inference_backend": "demo",
            "note": "Using fake detections for testing"
        }

    if mode == "hog":
        return {
            "status": "healthy",
            "model_loaded": True,
            "model_classes": ["person"],
            "inference_backend": "opencv_hog",
            "note": "Using OpenCV HOG (fallback mode)"
        }

    # Ultralytics mode
    if health.get("yolo_available"):
        return {
            "status": "healthy",
            "model_loaded": True,
            "model_classes": health.get("model_classes", ["person"]),
            "inference_backend": "ultralytics_yolo",
            "model_path": health.get("model_path"),
            "yolo_available": True,
        }

    # YOLO failed but HOG is available as fallback
    if health.get("fallback_available"):
        return {
            "status": "degraded",
            "model_loaded": False,
            "error": health.get("error", "YOLO not available"),
            "inference_backend": "opencv_hog",
            "message": "YOLO failed, using HOG fallback",
            "yolo_available": False,
            "hog_available": True,
        }

    # Both failed
    return {
        "status": "unhealthy",
        "model_loaded": False,
        "error": health.get("error", "All detection methods failed"),
        "inference_backend": "none",
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


def _congestion_level(count: int) -> str:
    if count <= 5:
        return "LOW"
    if count <= 15:
        return "MEDIUM"
    return "HIGH"


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
    except Exception as e:
        logger.error(f"Detection failed: {e}")
        raise RuntimeError(f"Detection failed: {e}") from e

    vis, api_dets, api_count, total_frame = render_queue_visual(bgr, detections, roi_norm)
    data_uri = encode_jpeg_data_uri(vis)
    persist_crowd_count(db, api_count)

    health = get_detector_health()
    backend = health.get("inference_backend", "opencv_hog")

    return {
        "count": api_count,
        "image": data_uri,
        "detections": [d.to_api_dict() for d in api_dets],
        "queue_zone_applied": roi_norm is not None,
        "total_persons_frame": total_frame,
        "congestion_level": _congestion_level(api_count),
        "inference_backend": backend,
    }


def start_background_yolo_warm() -> None:
    """Start background warmup of the YOLO model."""
    from app.services.yolo_manager import start_warmup
    if settings.YOLO_MODE == "ultralytics":
        logger.info("[YOLO] Starting background warmup...")
        start_warmup()
    else:
        logger.info(f"[YOLO] Skipping warmup - mode is {settings.YOLO_MODE}")

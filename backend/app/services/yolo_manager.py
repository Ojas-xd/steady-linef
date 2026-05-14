"""
YOLO People Detection via ONNX Runtime.

No PyTorch / ultralytics at runtime → fits comfortably in 512 MB.
Uses the same YOLOv8n weights exported to ONNX during the build step.
Falls back to OpenCV HOG if the ONNX model is not found.
"""
from __future__ import annotations

import gc
import logging
import math
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

ONNX_MODEL_FILENAME = "yolov8n.onnx"
PERSON_CONF = 0.25
IOU_THRESHOLD = 0.45
YOLO_INPUT_SIZE = 640     # must match export imgsz
MAX_INPUT_SIDE = 960


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


# ── Helpers ─────────────────────────────────────────────────────────────────

def _nms(boxes: np.ndarray, scores: np.ndarray, iou_thr: float) -> list[int]:
    """Pure-numpy NMS. boxes: (N,4) xyxy; scores: (N,)."""
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]
        ix1 = np.maximum(x1[i], x1[rest])
        iy1 = np.maximum(y1[i], y1[rest])
        ix2 = np.minimum(x2[i], x2[rest])
        iy2 = np.minimum(y2[i], y2[rest])
        inter = np.maximum(0.0, ix2 - ix1) * np.maximum(0.0, iy2 - iy1)
        iou = inter / (areas[i] + areas[rest] - inter + 1e-6)
        order = rest[iou <= iou_thr]
    return keep


def _letterbox(img: np.ndarray, size: int) -> tuple[np.ndarray, float, int, int]:
    """Resize keeping aspect ratio and pad to square. Returns (img, scale, padX, padY)."""
    h, w = img.shape[:2]
    scale = size / max(h, w)
    nh, nw = int(round(h * scale)), int(round(w * scale))
    img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    pad_top = (size - nh) // 2
    pad_left = (size - nw) // 2
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    canvas[pad_top:pad_top + nh, pad_left:pad_left + nw] = img
    return canvas, scale, pad_left, pad_top


def _preprocess(bgr: np.ndarray, size: int) -> tuple[np.ndarray, float, int, int]:
    """BGR → (1, 3, size, size) float32 [0,1] RGB + letterbox metadata."""
    lb, scale, px, py = _letterbox(bgr, size)
    rgb = cv2.cvtColor(lb, cv2.COLOR_BGR2RGB)
    tensor = rgb.astype(np.float32) / 255.0
    tensor = np.transpose(tensor, (2, 0, 1))[np.newaxis]   # (1,3,H,W)
    return np.ascontiguousarray(tensor), scale, px, py


def _postprocess(
    raw: np.ndarray,
    orig_w: int,
    orig_h: int,
    scale: float,
    pad_x: int,
    pad_y: int,
    conf_thr: float,
    iou_thr: float,
) -> list[PersonDetection]:
    """
    Decode YOLOv8 ONNX output (1, 84, 8400) → PersonDetection list.
    First 4 rows: cx,cy,w,h in letterboxed-pixel space.
    Rows 4-84: class probabilities.
    """
    pred = raw[0]                   # (84, 8400)
    pred = pred.T                   # (8400, 84)

    cx, cy, bw, bh = pred[:, 0], pred[:, 1], pred[:, 2], pred[:, 3]
    class_scores = pred[:, 4:]     # (8400, 80)

    person_scores = class_scores[:, 0]   # class 0 = person
    mask = person_scores >= conf_thr
    if not mask.any():
        return []

    cx, cy, bw, bh = cx[mask], cy[mask], bw[mask], bh[mask]
    scores = person_scores[mask]

    # cxcywh → xyxy (letterbox pixels)
    x1 = cx - bw / 2
    y1 = cy - bh / 2
    x2 = cx + bw / 2
    y2 = cy + bh / 2

    # Remove letterbox padding and scale back to original image
    x1 = (x1 - pad_x) / scale
    y1 = (y1 - pad_y) / scale
    x2 = (x2 - pad_x) / scale
    y2 = (y2 - pad_y) / scale

    x1 = np.clip(x1, 0, orig_w)
    y1 = np.clip(y1, 0, orig_h)
    x2 = np.clip(x2, 0, orig_w)
    y2 = np.clip(y2, 0, orig_h)

    boxes = np.stack([x1, y1, x2, y2], axis=1)
    keep = _nms(boxes, scores, iou_thr)

    out: list[PersonDetection] = []
    for i in keep:
        bx1, by1, bx2, by2 = int(boxes[i, 0]), int(boxes[i, 1]), int(boxes[i, 2]), int(boxes[i, 3])
        if bx2 - bx1 < 2 or by2 - by1 < 2:
            continue
        conf = float(min(0.99, max(0.01, float(scores[i]))))
        out.append(PersonDetection(bx1, by1, bx2, by2, conf))
    return out


# ── ONNX Manager ────────────────────────────────────────────────────────────

class YOLOManager:
    """Thread-safe people detector: ONNX Runtime primary, OpenCV HOG fallback."""

    def __init__(self) -> None:
        self._session: Any = None
        self._session_error: str | None = None
        self._lock = threading.Lock()
        self._infer_lock = threading.Lock()
        self._backend_dir = Path(__file__).resolve().parents[2]
        self._model_path = self._backend_dir / ONNX_MODEL_FILENAME
        self._hog: cv2.HOGDescriptor | None = None

    # ── ONNX session ──────────────────────────────────────────────────────

    def _load_session(self) -> bool:
        if self._session is not None:
            return True
        if self._session_error is not None:
            return False
        with self._lock:
            if self._session is not None:
                return True
            if self._session_error is not None:
                return False
            if not self._model_path.exists():
                self._session_error = (
                    f"ONNX model not found at {self._model_path}. "
                    "Run setup_yolo.py during build to generate it."
                )
                logger.error("[YOLO] %s", self._session_error)
                return False
            try:
                import onnxruntime as ort
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 1
                opts.inter_op_num_threads = 1
                opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                t0 = time.time()
                self._session = ort.InferenceSession(
                    str(self._model_path),
                    sess_options=opts,
                    providers=["CPUExecutionProvider"],
                )
                logger.info("[YOLO] ONNX session ready in %.2fs", time.time() - t0)
                return True
            except Exception as exc:
                import traceback
                self._session_error = str(exc)
                logger.error("[YOLO] ONNX load failed: %s\n%s", exc, traceback.format_exc())
                return False

    def _infer_onnx(self, bgr: np.ndarray) -> list[PersonDetection]:
        orig_h, orig_w = bgr.shape[:2]
        tensor, scale, px, py = _preprocess(bgr, YOLO_INPUT_SIZE)
        input_name = self._session.get_inputs()[0].name
        with self._infer_lock:
            raw = self._session.run(None, {input_name: tensor})[0]
        dets = _postprocess(raw, orig_w, orig_h, scale, px, py, PERSON_CONF, IOU_THRESHOLD)
        del raw
        gc.collect(0)
        return dets

    # ── HOG fallback ──────────────────────────────────────────────────────

    def _get_hog(self) -> cv2.HOGDescriptor:
        if self._hog is None:
            self._hog = cv2.HOGDescriptor()
            self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        return self._hog

    def _infer_hog(self, bgr: np.ndarray) -> list[PersonDetection]:
        hog = self._get_hog()
        rects, weights = hog.detectMultiScale(bgr, winStride=(8, 8), padding=(8, 8), scale=1.05)
        hh, ww = bgr.shape[:2]
        out: list[PersonDetection] = []
        for i, (x, y, rw, rh) in enumerate(rects):
            x1, y1, x2, y2 = int(x), int(y), int(x + rw), int(y + rh)
            raw_w = 0.5
            if len(weights) > i and len(weights[i]) > 0:
                try:
                    raw_w = float(weights[i][0])
                except Exception:
                    pass
            conf = float(min(0.99, max(PERSON_CONF, abs(raw_w) / 3.0)))
            x1 = max(0, min(x1, ww - 1))
            y1 = max(0, min(y1, hh - 1))
            x2 = max(x1 + 2, min(x2, ww))
            y2 = max(y1 + 2, min(y2, hh))
            if x2 - x1 >= 2 and y2 - y1 >= 2:
                out.append(PersonDetection(x1, y1, x2, y2, conf))
        return out

    # ── Public API ────────────────────────────────────────────────────────

    def detect(self, bgr: np.ndarray, force_hog: bool = False) -> list[PersonDetection]:
        if bgr.ndim != 3 or bgr.shape[2] != 3:
            raise ValueError("Expected HxWx3 BGR image")
        # Downscale very large images before detection
        hh, ww = bgr.shape[:2]
        m = max(hh, ww)
        if m > MAX_INPUT_SIDE:
            scale = MAX_INPUT_SIDE / m
            bgr = cv2.resize(bgr, (int(ww * scale), int(hh * scale)), interpolation=cv2.INTER_AREA)

        if not force_hog and self._load_session():
            try:
                return self._infer_onnx(bgr)
            except Exception as exc:
                logger.warning("[YOLO] ONNX inference failed, using HOG: %s", exc)

        return self._infer_hog(bgr)

    def health_check(self) -> dict[str, Any]:
        onnx_ok = self._load_session()
        return {
            "yolo_available": onnx_ok,
            "model_loaded": self._session is not None,
            "model_path": str(self._model_path),
            "model_exists": self._model_path.exists(),
            "inference_backend": "onnxruntime" if onnx_ok else "opencv_hog",
            "fallback_available": True,
            **({"error": self._session_error} if self._session_error else {}),
        }


# ── Singleton ────────────────────────────────────────────────────────────────

_manager: YOLOManager | None = None
_manager_lock = threading.Lock()


def get_yolo_manager() -> YOLOManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = YOLOManager()
    return _manager


def detect_people(bgr: np.ndarray, prefer_yolo: bool = True) -> list[PersonDetection]:
    return get_yolo_manager().detect(bgr, force_hog=not prefer_yolo)


def get_detector_health() -> dict[str, Any]:
    return get_yolo_manager().health_check()


def start_warmup() -> None:
    def _warm() -> None:
        try:
            get_yolo_manager()._load_session()
        except Exception as exc:
            logger.warning("[YOLO] warmup failed: %s", exc)
    threading.Thread(target=_warm, name="yolo-warmup", daemon=True).start()

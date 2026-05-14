"""
YOLO Model Manager - Robust handling for people detection with automatic fallback.

Features:
- Auto-download YOLOv8n model if missing
- Verify model integrity before use
- Graceful fallback to HOG if YOLO fails
- Thread-safe model loading
- Memory-efficient inference
"""
from __future__ import annotations

import gc
import logging
import math
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.request import urlopen
from urllib.error import URLError
import time

import cv2
import numpy as np
import torch

logger = logging.getLogger(__name__)

# Model URL and path
YOLO_MODEL_URL = "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.pt"
MODEL_FILENAME = "yolov8n.pt"

# Detection settings
PERSON_CONF = 0.25
YOLO_IMGSZ = 320
MAX_INPUT_SIDE = 960
IOU_THRESHOLD = 0.45


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


class YOLOManager:
    """Thread-safe YOLO model manager with auto-download and fallback."""

    def __init__(self):
        self._model: Any = None
        self._model_error: str | None = None
        self._model_lock = threading.Lock()
        self._predict_lock = threading.Lock()
        self._last_used: float = 0
        self._download_attempted = False
        self._backend_dir = Path(__file__).resolve().parents[2]
        self._model_path = self._backend_dir / MODEL_FILENAME
        self._is_available = False
        self._hog_detector: cv2.HOGDescriptor | None = None

        # Configure torch for low memory usage
        torch.set_num_threads(1)
        if hasattr(torch, 'set_num_interop_threads'):
            torch.set_num_interop_threads(1)

    def _ensure_model_downloaded(self) -> bool:
        """Download YOLO model if not exists. Returns True if model is ready."""
        if self._model_path.exists():
            # Verify file is not corrupted (should be > 10MB)
            size = self._model_path.stat().st_size
            if size > 5_000_000:  # At least 5MB
                logger.info(f"[YOLO] Model exists: {self._model_path} ({size // 1024 // 1024}MB)")
                return True
            else:
                logger.warning(f"[YOLO] Model file too small ({size} bytes), re-downloading...")
                self._model_path.unlink()

        if self._download_attempted:
            return self._model_path.exists()

        self._download_attempted = True
        logger.info(f"[YOLO] Downloading model from {YOLO_MODEL_URL}...")

        try:
            # Download with progress
            req = urlopen(YOLO_MODEL_URL, timeout=60)
            total_size = int(req.headers.get('Content-Length', 0))
            downloaded = 0
            chunk_size = 8192

            with open(self._model_path, 'wb') as f:
                while True:
                    chunk = req.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0 and downloaded % (1024 * 1024) < chunk_size:
                        pct = (downloaded / total_size) * 100
                        logger.info(f"[YOLO] Download progress: {pct:.1f}%")

            size = self._model_path.stat().st_size
            logger.info(f"[YOLO] Model downloaded successfully: {size // 1024 // 1024}MB")
            return True

        except URLError as e:
            logger.error(f"[YOLO] Download failed (network): {e}")
            return False
        except Exception as e:
            logger.error(f"[YOLO] Download failed: {e}")
            return False

    def _load_model(self) -> bool:
        """Load the YOLO model. Returns True on success."""
        if self._model is not None:
            return True
        if self._model_error is not None:
            return False

        with self._model_lock:
            if self._model is not None:
                return True
            if self._model_error is not None:
                return False

            try:
                # Ensure model is downloaded
                if not self._ensure_model_downloaded():
                    raise RuntimeError("Model download failed or file not available")

                # Import here to avoid heavy import at startup
                from ultralytics import YOLO

                logger.info(f"[YOLO] Loading model from {self._model_path}...")
                start_time = time.time()

                self._model = YOLO(str(self._model_path))

                # Warm up with dummy inference
                dummy = np.zeros((320, 320, 3), dtype=np.uint8)
                with torch.inference_mode():
                    self._model.predict(
                        dummy,
                        verbose=False,
                        conf=PERSON_CONF,
                        device="cpu",
                        imgsz=YOLO_IMGSZ
                    )
                del dummy
                gc.collect()

                load_time = time.time() - start_time
                logger.info(f"[YOLO] Model loaded successfully in {load_time:.2f}s")
                self._is_available = True
                return True

            except Exception as e:
                import traceback
                self._model_error = str(e)
                logger.error(f"[YOLO] Model load failed: {e}\n{traceback.format_exc()}")
                self._is_available = False
                return False

    def _get_hog_detector(self) -> cv2.HOGDescriptor:
        """Get or create HOG detector as fallback."""
        if self._hog_detector is None:
            self._hog_detector = cv2.HOGDescriptor()
            self._hog_detector.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        return self._hog_detector

    def _detect_hog(self, bgr: np.ndarray) -> list[PersonDetection]:
        """HOG-based person detection (fallback)."""
        hog = self._get_hog_detector()
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

            # Clamp to frame
            x1 = max(0, min(x1, ww - 1))
            y1 = max(0, min(y1, hh - 1))
            x2 = max(x1 + 2, min(x2, ww))
            y2 = max(y1 + 2, min(y2, hh))

            if x2 - x1 >= 2 and y2 - y1 >= 2:
                out.append(PersonDetection(x1, y1, x2, y2, conf))

        return out

    def _downscale_if_needed(self, bgr: np.ndarray) -> np.ndarray:
        """Downscale large images for faster inference."""
        hh, ww = bgr.shape[:2]
        m = max(hh, ww)
        if m <= MAX_INPUT_SIDE:
            return bgr
        scale = MAX_INPUT_SIDE / m
        nw, nh = max(1, int(ww * scale)), max(1, int(hh * scale))
        return cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_AREA)

    def detect(self, bgr: np.ndarray, force_hog: bool = False) -> list[PersonDetection]:
        """
        Detect people in image.

        Args:
            bgr: BGR image (OpenCV format)
            force_hog: Force use of HOG detector even if YOLO is available

        Returns:
            List of PersonDetection objects
        """
        if bgr.ndim != 3 or bgr.shape[2] != 3:
            raise ValueError("Expected HxWx3 BGR image")

        # Preprocess
        work = self._downscale_if_needed(bgr).copy()
        hh, ww = work.shape[:2]

        # Try YOLO first (unless forced HOG)
        if not force_hog and self._load_model():
            try:
                with self._predict_lock:
                    with torch.inference_mode():
                        results = self._model.predict(
                            work,
                            verbose=False,
                            conf=PERSON_CONF,
                            iou=IOU_THRESHOLD,
                            classes=[0],  # person class only
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
                        if cls_id != 0 or conf < PERSON_CONF or not math.isfinite(conf):
                            continue
                        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

                        # Clamp to frame
                        x1 = max(0, min(x1, ww - 1))
                        y1 = max(0, min(y1, hh - 1))
                        x2 = max(x1 + 2, min(x2, ww))
                        y2 = max(y1 + 2, min(y2, hh))

                        if x2 - x1 >= 2 and y2 - y1 >= 2:
                            out.append(PersonDetection(x1, y1, x2, y2, conf))

                self._last_used = time.time()

                # Clean up memory
                del results
                gc.collect()

                return out

            except Exception as e:
                logger.warning(f"[YOLO] Inference failed, falling back to HOG: {e}")
                # Fall through to HOG

        # Fallback to HOG
        return self._detect_hog(work)

    def health_check(self) -> dict[str, Any]:
        """Get health status of the detector."""
        status = {
            "yolo_available": self._is_available,
            "model_loaded": self._model is not None,
            "model_path": str(self._model_path),
            "model_exists": self._model_path.exists(),
            "fallback_available": True,  # HOG is always available
        }

        if self._model_error:
            status["error"] = self._model_error

        if self._model is not None:
            try:
                names = list(self._model.names.values()) if hasattr(self._model, "names") else []
                status["model_classes"] = names
                status["person_class_available"] = "person" in names or 0 in names
            except Exception as e:
                status["class_error"] = str(e)

        return status

    def get_preferred_backend(self) -> str:
        """Return the preferred detection backend."""
        if self._load_model():
            return "ultralytics_yolo"
        return "opencv_hog"


# Global singleton instance
_yolo_manager: YOLOManager | None = None
_manager_lock = threading.Lock()


def get_yolo_manager() -> YOLOManager:
    """Get the global YOLO manager instance."""
    global _yolo_manager
    if _yolo_manager is None:
        with _manager_lock:
            if _yolo_manager is None:
                _yolo_manager = YOLOManager()
    return _yolo_manager


def detect_people(bgr: np.ndarray, prefer_yolo: bool = True) -> list[PersonDetection]:
    """
    Convenience function to detect people.

    Args:
        bgr: BGR image
        prefer_yolo: Try YOLO first, fallback to HOG if fails

    Returns:
        List of detections
    """
    manager = get_yolo_manager()
    return manager.detect(bgr, force_hog=not prefer_yolo)


def get_detector_health() -> dict[str, Any]:
    """Get health status."""
    return get_yolo_manager().health_check()


def start_warmup() -> None:
    """Start background warmup of the model."""
    def _warm():
        try:
            manager = get_yolo_manager()
            manager._load_model()
        except Exception as e:
            logger.warning(f"[YOLO] Background warmup failed: {e}")

    threading.Thread(target=_warm, name="yolo-warmup", daemon=True).start()

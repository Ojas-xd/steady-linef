#!/usr/bin/env python3
"""
BUILD-TIME setup script.

Strategy (fastest → slowest):
  1. Download a pre-built YOLOv8n ONNX from Hugging Face (no torch needed,
     avoids torch 2.7 dynamo-exporter / IR-v13 issue entirely).
  2. If download fails → export from .pt using ultralytics with torch<2.6
     (old exporter → IR v7 → onnxruntime compatible).

Render build command (Strategy 1 — recommended):
    pip install -r requirements.txt && python setup_yolo.py

Render build command (Strategy 2 — if download fails):
    pip install -r requirements.txt && pip install "torch<2.6" "ultralytics==8.2.100" && python setup_yolo.py
"""
import os
import sys
import time
import struct
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

os.environ.setdefault("YOLO_VERBOSE", "False")

BACKEND_DIR = Path(__file__).resolve().parent
ONNX_PATH = BACKEND_DIR / "yolov8n.onnx"
EXPORT_IMGSZ = 640
MIN_ONNX_BYTES = 5_000_000   # 5 MB sanity check

# Pre-built YOLOv8n ONNX sources (IR v7–9, opset 17, onnxruntime-compatible)
DOWNLOAD_URLS = [
    "https://huggingface.co/Ultralytics/Assets/resolve/main/yolov8n.onnx",
    "https://huggingface.co/ultralytics/assets/resolve/main/yolov8n.onnx",
    "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.onnx",
]


def _log(tag: str, msg: str) -> None:
    colours = {"INFO": "\033[94m", "OK": "\033[92m", "WARN": "\033[93m", "ERR": "\033[91m"}
    print(f"{colours.get(tag, '')}[{tag}]\033[0m {msg}", flush=True)


def _onnx_ir_version(path: Path) -> int | None:
    """Read the ONNX IR version from the protobuf header without loading full model."""
    try:
        with open(path, "rb") as f:
            data = f.read(64)
        # ONNX ModelProto: field 1 = ir_version (int64), field 8 = model_version
        # Protobuf wire: tag=(field<<3|type), varint
        i = 0
        while i < len(data):
            tag_byte = data[i]; i += 1
            field_num = tag_byte >> 3
            wire_type = tag_byte & 0x07
            if wire_type == 0:   # varint
                val = 0; shift = 0
                while True:
                    b = data[i]; i += 1
                    val |= (b & 0x7F) << shift
                    shift += 7
                    if not (b & 0x80):
                        break
                if field_num == 1:   # ir_version
                    return val
            else:
                break
    except Exception:
        pass
    return None


def _download_onnx() -> bool:
    """Try each URL in DOWNLOAD_URLS; return True on first success."""
    for url in DOWNLOAD_URLS:
        _log("INFO", f"Trying: {url}")
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=120) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                tmp = ONNX_PATH.with_suffix(".tmp")
                with open(tmp, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                if downloaded < MIN_ONNX_BYTES:
                    tmp.unlink(missing_ok=True)
                    _log("WARN", f"Downloaded only {downloaded} bytes — skipping.")
                    continue
                tmp.rename(ONNX_PATH)
                size_mb = ONNX_PATH.stat().st_size / 1024 / 1024
                _log("OK", f"Downloaded {size_mb:.1f} MB from {url}")
                return True
        except Exception as exc:
            _log("WARN", f"Download failed ({exc}), trying next URL…")
    return False


def _export_onnx() -> bool:
    """
    Export from .pt using ultralytics.
    REQUIRES torch<2.6 in build to use old ONNX exporter → IR v7 (not IR v13).
    """
    try:
        from ultralytics import YOLO
    except ImportError:
        _log("ERR", "ultralytics not installed. Use build command with 'torch<2.6 ultralytics==8.2.100'")
        return False

    _log("INFO", "Loading YOLOv8n weights (downloads if missing)…")
    t0 = time.time()
    try:
        model = YOLO("yolov8n.pt")
    except Exception as exc:
        _log("ERR", f"Failed to load yolov8n.pt: {exc}")
        return False
    _log("INFO", f"Weights ready in {time.time()-t0:.1f}s")

    _log("INFO", f"Exporting to ONNX (imgsz={EXPORT_IMGSZ})…")
    t0 = time.time()
    try:
        result = model.export(format="onnx", imgsz=EXPORT_IMGSZ, simplify=True,
                              opset=17, dynamic=False)
        exported = Path(str(result))
        if exported.resolve() != ONNX_PATH.resolve():
            exported.rename(ONNX_PATH)
    except Exception as exc:
        _log("ERR", f"Export failed: {exc}")
        return False

    for pt in BACKEND_DIR.glob("*.pt"):
        pt.unlink()
        _log("INFO", f"Deleted {pt.name}")

    if not ONNX_PATH.exists() or ONNX_PATH.stat().st_size < MIN_ONNX_BYTES:
        _log("ERR", "ONNX file missing or too small after export.")
        return False

    size_mb = ONNX_PATH.stat().st_size / 1024 / 1024
    _log("OK", f"Exported in {time.time()-t0:.1f}s → {ONNX_PATH} ({size_mb:.1f} MB)")
    return True


def get_or_build_onnx() -> bool:
    """Get the ONNX model: skip if exists, otherwise download then export."""
    if ONNX_PATH.exists() and ONNX_PATH.stat().st_size > MIN_ONNX_BYTES:
        _log("OK", f"ONNX already present ({ONNX_PATH.stat().st_size // 1024 // 1024} MB) — skip.")
        return True

    _log("INFO", "Step 1: Download pre-built ONNX (avoids torch dynamo IR-v13 issue)…")
    if _download_onnx():
        return True

    _log("WARN", "All downloads failed. Step 2: Exporting from .pt…")
    _log("INFO", "IR v13 from torch 2.7+ will be auto-patched to IR v9 after export.")
    return _export_onnx()


def _patch_ir_version() -> bool:
    """
    If the exported ONNX has IR version > 10 (generated by torch 2.6+ dynamo
    exporter), patch it down to IR v9 so onnxruntime 1.19.x can load it.
    YOLOv8n only uses standard ops available since IR v4, so the downgrade is safe.
    """
    ir = _onnx_ir_version(ONNX_PATH)
    if ir is None or ir <= 10:
        return True   # already fine

    _log("WARN", f"ONNX IR version is {ir} (too new). Patching to IR v9…")
    try:
        import onnx
        model = onnx.load(str(ONNX_PATH))
        model.ir_version = 9
        onnx.save(model, str(ONNX_PATH))
        _log("OK", f"Patched IR version {ir} → 9 (onnxruntime compatible)")
        return True
    except ImportError:
        _log("ERR", "onnx package not available — cannot patch IR version.")
        _log("ERR", "Add 'onnx>=1.14.0' to requirements.txt")
        return False
    except Exception as exc:
        _log("ERR", f"IR version patch failed: {exc}")
        return False


def verify_onnx() -> bool:
    """Smoke-test with onnxruntime + check IR version."""
    if not _patch_ir_version():
        ONNX_PATH.unlink(missing_ok=True)
        return False

    ir = _onnx_ir_version(ONNX_PATH)
    if ir is not None:
        _log("INFO", f"ONNX IR version: {ir} (compatible ✓)")

    try:
        import onnxruntime as ort
        import numpy as np
    except ImportError:
        _log("WARN", "onnxruntime not installed — skipping smoke test.")
        return True

    try:
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        sess = ort.InferenceSession(str(ONNX_PATH), sess_options=opts,
                                    providers=["CPUExecutionProvider"])
        dummy = np.zeros((1, 3, EXPORT_IMGSZ, EXPORT_IMGSZ), dtype=np.float32)
        name = sess.get_inputs()[0].name
        out = sess.run(None, {name: dummy})
        _log("OK", f"Smoke-test passed. Output shape: {out[0].shape}")
        return True
    except Exception as exc:
        _log("ERR", f"Smoke-test failed: {exc}")
        ONNX_PATH.unlink(missing_ok=True)
        return False


def main() -> None:
    print("\n" + "="*60)
    print("YOLOv8n ONNX setup for Crowd Detection")
    print("="*60 + "\n")

    if not get_or_build_onnx():
        _log("ERR", "Could not obtain ONNX model. Try build command:")
        _log("ERR", '  pip install -r requirements.txt && pip install "torch<2.6" ultralytics==8.2.100 && python setup_yolo.py')
        sys.exit(1)

    if not verify_onnx():
        _log("ERR", "Verification failed. Regenerate with: pip install 'torch<2.6' ultralytics==8.2.100 && python setup_yolo.py")
        sys.exit(1)

    print("\n" + "="*60)
    print("Setup complete — yolov8n.onnx ready (onnxruntime, no torch at runtime).")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
BUILD-TIME setup script.
Downloads YOLOv8n.pt via ultralytics, exports to yolov8n.onnx, then deletes the .pt.
At runtime the app only uses onnxruntime (no torch / ultralytics needed → fits in 512 MB).

Render build command:
    pip install -r requirements.txt && pip install ultralytics==8.2.100 && python setup_yolo.py
"""
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("YOLO_VERBOSE", "False")

BACKEND_DIR = Path(__file__).resolve().parent
PT_PATH = BACKEND_DIR / "yolov8n.pt"
ONNX_PATH = BACKEND_DIR / "yolov8n.onnx"
EXPORT_IMGSZ = 640


def _log(tag: str, msg: str) -> None:
    colours = {"INFO": "\033[94m", "OK": "\033[92m", "WARN": "\033[93m", "ERR": "\033[91m"}
    print(f"{colours.get(tag, '')}[{tag}]\033[0m {msg}", flush=True)


def export_onnx() -> bool:
    """Use ultralytics (build-time only) to produce yolov8n.onnx."""
    if ONNX_PATH.exists() and ONNX_PATH.stat().st_size > 5_000_000:
        _log("OK", f"ONNX model already exists ({ONNX_PATH.stat().st_size // 1024 // 1024} MB) — skipping export.")
        return True

    try:
        from ultralytics import YOLO
    except ImportError:
        _log("ERR", "ultralytics not installed. Add it to the build command:")
        _log("ERR", "  pip install ultralytics==8.2.100 && python setup_yolo.py")
        return False

    # Download .pt if needed (ultralytics handles this automatically)
    _log("INFO", f"Loading YOLOv8n weights (downloads if missing)…")
    t0 = time.time()
    try:
        model = YOLO("yolov8n.pt")
    except Exception as exc:
        _log("ERR", f"Failed to load/download yolov8n.pt: {exc}")
        return False
    _log("INFO", f"Weights loaded in {time.time()-t0:.1f}s")

    # Export to ONNX
    _log("INFO", f"Exporting to ONNX (imgsz={EXPORT_IMGSZ})…")
    t0 = time.time()
    try:
        export_result = model.export(
            format="onnx",
            imgsz=EXPORT_IMGSZ,
            simplify=True,
            opset=17,
            dynamic=False,
        )
        exported = Path(str(export_result))
    except Exception as exc:
        _log("ERR", f"Export failed: {exc}")
        return False

    # ultralytics saves next to the .pt — move to backend dir if needed
    if exported.resolve() != ONNX_PATH.resolve():
        exported.rename(ONNX_PATH)

    if not ONNX_PATH.exists() or ONNX_PATH.stat().st_size < 1_000_000:
        _log("ERR", "ONNX file missing or too small after export.")
        return False

    size_mb = ONNX_PATH.stat().st_size / 1024 / 1024
    _log("OK", f"ONNX exported in {time.time()-t0:.1f}s → {ONNX_PATH} ({size_mb:.1f} MB)")

    # Remove .pt to save disk space on Render
    for pt in BACKEND_DIR.glob("*.pt"):
        pt.unlink()
        _log("INFO", f"Deleted {pt.name} (not needed at runtime)")

    return True


def verify_onnx() -> bool:
    """Quick smoke-test of the exported ONNX model with onnxruntime."""
    try:
        import onnxruntime as ort
        import numpy as np
    except ImportError:
        _log("WARN", "onnxruntime not installed yet — skipping smoke test.")
        return True

    try:
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        sess = ort.InferenceSession(str(ONNX_PATH), sess_options=opts, providers=["CPUExecutionProvider"])
        dummy = np.zeros((1, 3, EXPORT_IMGSZ, EXPORT_IMGSZ), dtype=np.float32)
        input_name = sess.get_inputs()[0].name
        out = sess.run(None, {input_name: dummy})
        _log("OK", f"ONNX smoke-test passed. Output shape: {out[0].shape}")
        return True
    except Exception as exc:
        _log("ERR", f"ONNX smoke-test failed: {exc}")
        return False


def main() -> None:
    print("\n" + "="*60)
    print("YOLOv8 → ONNX export for Crowd Detection")
    print("="*60 + "\n")

    if not export_onnx():
        sys.exit(1)

    if not verify_onnx():
        sys.exit(1)

    print("\n" + "="*60)
    print("Setup complete — yolov8n.onnx is ready.")
    print("Runtime uses onnxruntime only (no torch, fits in 512 MB).")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()

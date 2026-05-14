#!/usr/bin/env python3
"""
Setup script for YOLO model - Run this before starting the server.
Ensures model is downloaded and verified.
"""
import os
import sys
import time
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError

# Colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

MODEL_URL = "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.pt"
MODEL_NAME = "yolov8n.pt"

def log_info(msg: str):
    print(f"{BLUE}[INFO]{RESET} {msg}")

def log_success(msg: str):
    print(f"{GREEN}[SUCCESS]{RESET} {msg}")

def log_error(msg: str):
    print(f"{RED}[ERROR]{RESET} {msg}")

def log_warn(msg: str):
    print(f"{YELLOW}[WARN]{RESET} {msg}")

def get_backend_dir() -> Path:
    """Get the backend directory."""
    return Path(__file__).resolve().parent

def download_model() -> bool:
    """Download the YOLOv8n model."""
    backend_dir = get_backend_dir()
    model_path = backend_dir / MODEL_NAME

    if model_path.exists():
        size = model_path.stat().st_size
        size_mb = size / 1024 / 1024
        if size > 5_000_000:  # At least 5MB
            log_success(f"Model already exists: {model_path} ({size_mb:.1f} MB)")
            return True
        else:
            log_warn(f"Model file too small ({size} bytes), re-downloading...")
            model_path.unlink()

    log_info(f"Downloading YOLOv8n model from GitHub...")
    log_info(f"URL: {MODEL_URL}")
    log_info(f"Destination: {model_path}")

    try:
        req = urlopen(MODEL_URL, timeout=120)
        total_size = int(req.headers.get('Content-Length', 0))

        if total_size > 0:
            log_info(f"Expected size: {total_size / 1024 / 1024:.1f} MB")

        downloaded = 0
        chunk_size = 8192
        last_pct = -10

        with open(model_path, 'wb') as f:
            while True:
                chunk = req.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)

                if total_size > 0:
                    pct = int((downloaded / total_size) * 100)
                    if pct >= last_pct + 10:
                        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                        print(f"\r  Progress: [{bar}] {pct}% ({downloaded/1024/1024:.1f} MB)", end="", flush=True)
                        last_pct = pct

        print()  # New line after progress

        # Verify download
        final_size = model_path.stat().st_size
        if final_size < 5_000_000:
            log_error(f"Downloaded file too small ({final_size} bytes), may be corrupted")
            model_path.unlink()
            return False

        log_success(f"Model downloaded successfully: {final_size / 1024 / 1024:.1f} MB")
        return True

    except URLError as e:
        log_error(f"Network error: {e}")
        return False
    except KeyboardInterrupt:
        log_warn("Download interrupted by user")
        if model_path.exists():
            model_path.unlink()
        return False
    except Exception as e:
        log_error(f"Download failed: {e}")
        if model_path.exists():
            model_path.unlink()
        return False

def verify_model() -> bool:
    """Verify the model can be loaded."""
    backend_dir = get_backend_dir()
    model_path = backend_dir / MODEL_NAME

    if not model_path.exists():
        log_error("Model file not found")
        return False

    log_info("Verifying model can be loaded...")

    try:
        # Suppress ultralytics output
        os.environ["YOLO_VERBOSE"] = "False"

        from ultralytics import YOLO
        import torch
        import numpy as np

        # Load model
        start = time.time()
        model = YOLO(str(model_path))
        load_time = time.time() - start

        # Warmup inference
        log_info("Running warmup inference...")
        dummy = np.zeros((320, 320, 3), dtype=np.uint8)

        torch.set_num_threads(1)
        with torch.inference_mode():
            results = model.predict(dummy, verbose=False, conf=0.25, device="cpu", imgsz=320)

        log_success(f"Model verified! Load time: {load_time:.2f}s")

        # Check classes
        if hasattr(model, "names"):
            names = list(model.names.values())
            log_info(f"Available classes: {names[:10]}..." if len(names) > 10 else f"Available classes: {names}")
            if "person" in names:
                log_success("Person class is available!")
            else:
                log_warn("Person class not found in model!")

        return True

    except ImportError as e:
        log_error(f"Required package not installed: {e}")
        log_info("Run: pip install ultralytics torch opencv-python numpy")
        return False
    except Exception as e:
        log_error(f"Model verification failed: {e}")
        return False

def check_dependencies() -> bool:
    """Check if required dependencies are installed."""
    log_info("Checking dependencies...")

    required = [
        ("ultralytics", "ultralytics"),
        ("torch", "torch"),
        ("cv2", "opencv-python"),
        ("numpy", "numpy"),
        ("PIL", "pillow"),
    ]

    all_ok = True
    for module, package in required:
        try:
            __import__(module)
            log_success(f"  ✓ {package}")
        except ImportError:
            log_error(f"  ✗ {package} - NOT INSTALLED")
            all_ok = False

    if not all_ok:
        log_info("\nInstall missing packages with:")
        log_info("  pip install ultralytics torch opencv-python numpy pillow")

    return all_ok

def main():
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}YOLOv8 Setup for Crowd Detection{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")

    # Check dependencies first
    if not check_dependencies():
        log_error("Please install missing dependencies first")
        sys.exit(1)

    # Download model
    if not download_model():
        log_error("Failed to download model")
        sys.exit(1)

    # Verify model
    if not verify_model():
        log_error("Model verification failed")
        sys.exit(1)

    print(f"\n{GREEN}{'='*60}{RESET}")
    print(f"{GREEN}YOLO is ready for crowd detection!{RESET}")
    print(f"{GREEN}{'='*60}{RESET}\n")

    print("You can now:")
    print("  1. Start the backend server: python -m uvicorn app.main:app --reload")
    print("  2. Set YOLO_MODE=ultralytics in your .env file")
    print("  3. Open the Camera page to test person detection")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Download YOLO model before app starts."""
import os

MODEL_PATH = "yolov8n.pt"

if not os.path.exists(MODEL_PATH):
    print(f"Downloading YOLO model to {MODEL_PATH}...")
    try:
        from ultralytics import YOLO
        # This will auto-download if not exists
        model = YOLO(MODEL_PATH)
        print(f"✓ Model downloaded successfully")
    except Exception as e:
        print(f"✗ Failed to download model: {e}")
        exit(1)
else:
    print(f"✓ Model already exists at {MODEL_PATH}")

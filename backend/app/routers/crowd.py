import io
import base64
from datetime import datetime

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from PIL import Image
import numpy as np
import cv2

from app.database import get_db
from app.models import CrowdCount

router = APIRouter(prefix="/crowd", tags=["Crowd"])

# Lazy-load YOLO model
_model = None


def _get_model():
    global _model
    if _model is None:
        from ultralytics import YOLO
        from app.config import settings
        _model = YOLO(settings.YOLO_MODEL_PATH)
    return _model


@router.get("/count")
def get_live_count(db: Session = Depends(get_db)):
    latest = db.query(CrowdCount).order_by(CrowdCount.timestamp.desc()).first()
    return {
        "count": latest.count if latest else 0,
        "timestamp": latest.timestamp.isoformat() if latest else datetime.utcnow().isoformat(),
    }


@router.post("/analyze")
async def analyze_frame(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload an image frame → YOLO detects people → returns count + annotated image."""
    contents = await file.read()
    image = Image.open(io.BytesIO(contents))
    frame = np.array(image)
    
    # Convert RGB to BGR for OpenCV if needed
    if len(frame.shape) == 3 and frame.shape[2] == 3:
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    else:
        frame_bgr = frame

    model = _get_model()
    results = model(frame, verbose=False)

    # Class 0 = person in COCO
    count = 0
    detections = []
    
    for r in results:
        for box in r.boxes:
            if int(box.cls[0]) == 0:  # Person class
                count += 1
                # Get box coordinates
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                confidence = float(box.conf[0])
                
                detections.append({
                    "box": [x1, y1, x2, y2],
                    "confidence": round(confidence, 2)
                })
                
                # Draw bounding box (green)
                cv2.rectangle(frame_bgr, (x1, y1), (x2, y2), (0, 255, 0), 2)
                
                # Draw label with confidence
                label = f"Person {confidence:.2f}"
                label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
                cv2.rectangle(frame_bgr, (x1, y1 - label_size[1] - 10), (x1 + label_size[0], y1), (0, 255, 0), -1)
                cv2.putText(frame_bgr, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)

    # Convert back to RGB for output
    frame_annotated = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    
    # Convert to PIL and then to base64
    annotated_image = Image.fromarray(frame_annotated)
    buffered = io.BytesIO()
    annotated_image.save(buffered, format="JPEG", quality=85)
    img_base64 = base64.b64encode(buffered.getvalue()).decode()

    # Store the count
    record = CrowdCount(count=count, timestamp=datetime.utcnow())
    db.add(record)
    db.commit()

    return {
        "count": count,
        "image": f"data:image/jpeg;base64,{img_base64}",
        "detections": detections
    }

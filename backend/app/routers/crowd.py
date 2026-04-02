import io
from datetime import datetime

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session
from PIL import Image
import numpy as np

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
    """Upload an image frame → YOLO detects people → returns count."""
    contents = await file.read()
    image = Image.open(io.BytesIO(contents))
    frame = np.array(image)

    model = _get_model()
    results = model(frame, verbose=False)

    # Class 0 = person in COCO
    count = 0
    for r in results:
        for box in r.boxes:
            if int(box.cls[0]) == 0:
                count += 1

    # Store the count
    record = CrowdCount(count=count, timestamp=datetime.utcnow())
    db.add(record)
    db.commit()

    return {"count": count}

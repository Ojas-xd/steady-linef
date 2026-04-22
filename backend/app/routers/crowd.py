import io
import base64
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from PIL import Image
import numpy as np
import cv2

from app.database import get_db
from app.models import CrowdCount
from app.schemas import CrowdAnalyzeOut

router = APIRouter(prefix="/crowd", tags=["Crowd"])
logger = logging.getLogger(__name__)

# Lazy-load YOLO model
_model = None
_model_error = None


def _get_model():
    global _model, _model_error
    if _model is None and _model_error is None:
        try:
            from ultralytics import YOLO
            from app.config import settings
            import os
            
            logger.info(f"Loading YOLO model from: {settings.YOLO_MODEL_PATH}")
            
            # Check if model file exists
            if not os.path.exists(settings.YOLO_MODEL_PATH):
                logger.warning(f"Model file not found at {settings.YOLO_MODEL_PATH}, downloading...")
            
            # Load model - will auto-download if not present
            _model = YOLO(settings.YOLO_MODEL_PATH)
            
            # Warm up model with dummy inference
            import numpy as np
            dummy = np.zeros((640, 480, 3), dtype=np.uint8)
            _model.predict(dummy, verbose=False, conf=0.25)
            
            logger.info(f"YOLO model loaded successfully. Classes: {len(_model.names)}")
        except Exception as e:
            _model_error = str(e)
            logger.error(f"Failed to load YOLO model: {e}")
    if _model_error:
        raise HTTPException(status_code=503, detail=f"YOLO model not available: {_model_error}")
    return _model


@router.get("/count")
def get_live_count(db: Session = Depends(get_db)):
    """Get latest crowd count, but only if it's recent (within last 5 minutes)"""
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    
    # Only get counts from last 5 minutes to avoid showing stale data
    latest = db.query(CrowdCount).filter(CrowdCount.timestamp >= cutoff).order_by(CrowdCount.timestamp.desc()).first()
    
    return {
        "count": latest.count if latest else 0,
        "timestamp": latest.timestamp.isoformat() if latest else datetime.utcnow().isoformat(),
    }


@router.post("/analyze", response_model=CrowdAnalyzeOut)
async def analyze_frame(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload an image frame → YOLO detects people → returns count + annotated image."""
    try:
        contents = await file.read()
        if not contents:
            raise HTTPException(status_code=400, detail="Empty file uploaded")
        
        image = Image.open(io.BytesIO(contents))
        
        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        frame = np.array(image)
        
        # Validate frame dimensions
        if len(frame.shape) != 3 or frame.shape[2] != 3:
            raise HTTPException(status_code=400, detail=f"Invalid image dimensions: {frame.shape}")
            
        logger.info(f"Processing image: shape={frame.shape}, size={len(contents)} bytes")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process uploaded image: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid image file: {str(e)}")
    
    # Convert RGB to BGR for OpenCV if needed
    if len(frame.shape) == 3 and frame.shape[2] == 3:
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    else:
        frame_bgr = frame

    try:
        model = _get_model()
        # Use predict with explicit confidence threshold and classes (0 = person)
        results = model.predict(
            frame, 
            verbose=False, 
            conf=0.25,  # Confidence threshold 25%
            iou=0.45,   # NMS IoU threshold
            classes=[0],  # Only detect class 0 (person)
            device='cpu'  # Force CPU to avoid GPU issues
        )
        logger.info(f"YOLO inference completed, processing {len(results)} result(s)")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"YOLO inference failed: {e}")
        raise HTTPException(status_code=500, detail=f"YOLO analysis failed: {str(e)}")

    # Class 0 = person in COCO
    count = 0
    detections = []
    
    for r in results:
        logger.debug(f"Result boxes: {len(r.boxes)}")
        for box in r.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            
            # Only count person class (0) with confidence >= 0.25
            if cls_id == 0 and conf >= 0.25:
                count += 1
                # Get box coordinates
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                
                detections.append({
                    "box": [x1, y1, x2, y2],
                    "confidence": round(conf, 2)
                })
                
                # Draw bounding box (green)
                cv2.rectangle(frame_bgr, (x1, y1), (x2, y2), (0, 255, 0), 2)
                
                # Draw label with confidence
                label = f"Person {conf:.2f}"
                label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2)[0]
                cv2.rectangle(frame_bgr, (x1, y1 - label_size[1] - 10), (x1 + label_size[0], y1), (0, 255, 0), -1)
                cv2.putText(frame_bgr, label, (x1, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
    
    logger.info(f"Detection complete: {count} person(s) found with {len(detections)} detection record(s)")

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

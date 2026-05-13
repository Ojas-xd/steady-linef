"""HTTP surface for crowd / queue camera. Domain logic is in ``app.services.crowd_queue``."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CrowdCount
from app.schemas import CrowdAnalyzeOut
from app.services.crowd_queue import (
    analyze_frame_pipeline,
    health_payload,
    start_background_yolo_warm,
)

router = APIRouter(prefix="/crowd", tags=["Crowd"])
logger = logging.getLogger(__name__)


@router.get("/health")
def crowd_health_check():
    return health_payload()


@router.get("/count")
def get_live_count(db: Session = Depends(get_db)):
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    latest = (
        db.query(CrowdCount)
        .filter(CrowdCount.timestamp >= cutoff)
        .order_by(CrowdCount.timestamp.desc())
        .first()
    )
    return {
        "count": latest.count if latest else 0,
        "timestamp": latest.timestamp.isoformat() if latest else datetime.utcnow().isoformat(),
    }


@router.post("/analyze", response_model=CrowdAnalyzeOut)
async def analyze_frame(
    file: UploadFile = File(...),
    roi_x: str | None = Form(default=None),
    roi_y: str | None = Form(default=None),
    roi_w: str | None = Form(default=None),
    roi_h: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    logger.info("POST /crowd/analyze filename=%s", file.filename)
    try:
        contents = await file.read()
        return analyze_frame_pipeline(
            contents=contents,
            roi_x=roi_x,
            roi_y=roi_y,
            roi_w=roi_w,
            roi_h=roi_h,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        logger.exception("crowd analyze failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}") from e

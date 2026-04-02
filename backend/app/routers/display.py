from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Token, TokenStatus, CrowdCount
from app.schemas import NowServingOut

router = APIRouter(prefix="/display", tags=["Display"])


@router.get("/now-serving", response_model=NowServingOut)
def get_now_serving(db: Session = Depends(get_db)):
    serving = db.query(Token).filter(Token.status == TokenStatus.serving).order_by(Token.served_at.desc()).first()
    upcoming = (
        db.query(Token)
        .filter(Token.status == TokenStatus.waiting)
        .order_by(Token.issued_at.asc())
        .limit(5)
        .all()
    )
    latest_crowd = db.query(CrowdCount).order_by(CrowdCount.timestamp.desc()).first()

    return NowServingOut(
        serving_token=serving.token_number if serving else None,
        serving_counter=serving.counter if serving else None,
        upcoming_tokens=[t.token_number for t in upcoming],
        live_count=latest_crowd.count if latest_crowd else 0,
    )

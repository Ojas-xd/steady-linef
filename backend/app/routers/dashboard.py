from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Token, TokenStatus, CrowdCount
from app.schemas import DashboardStats

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardStats)
def get_stats(db: Session = Depends(get_db)):
    active = db.query(Token).filter(Token.status.in_([TokenStatus.waiting, TokenStatus.serving])).count()

    avg_wait = db.query(func.avg(Token.service_time)).filter(Token.service_time.isnot(None)).scalar() or 0

    # Peak hour from completed tokens
    peak = (
        db.query(func.strftime("%H", Token.issued_at).label("hr"), func.count().label("cnt"))
        .filter(Token.status == TokenStatus.completed)
        .group_by("hr")
        .order_by(func.count().desc())
        .first()
    )
    peak_hour = f"{int(peak.hr)}:00" if peak else "N/A"

    # Latest crowd count
    latest_crowd = db.query(CrowdCount).order_by(CrowdCount.timestamp.desc()).first()
    live = latest_crowd.count if latest_crowd else 0

    return DashboardStats(
        live_count=live,
        active_tokens=active,
        avg_wait_minutes=round(avg_wait, 1),
        peak_hour=peak_hour,
    )


@router.get("/forecast")
def get_forecast(db: Session = Depends(get_db)):
    """Return Prophet-powered hourly forecast vs actual counts."""
    from app.forecaster import forecast_hourly
    return forecast_hourly(db, hours_ahead=8, source="tokens")


@router.get("/weekly-forecast")
def get_weekly_forecast(db: Session = Depends(get_db)):
    """Return Prophet-powered weekly crowd forecast."""
    from app.forecaster import forecast_weekly
    return forecast_weekly(db)

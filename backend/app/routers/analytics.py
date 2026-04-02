from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Token, TokenStatus, CrowdCount
from app.schemas import AnalyticsOut, TokenOut

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/", response_model=AnalyticsOut)
def get_analytics(date: str | None = Query(None), db: Session = Depends(get_db)):
    query = db.query(Token).filter(Token.status == TokenStatus.completed)
    if date:
        query = query.filter(func.date(Token.completed_at) == date)

    completed = query.all()
    tokens_served = len(completed)

    avg_svc = 0.0
    if completed:
        times = [t.service_time for t in completed if t.service_time]
        avg_svc = round(sum(times) / len(times), 1) if times else 0.0

    # Peak hour
    peak = (
        db.query(func.strftime("%H", Token.issued_at).label("hr"), func.count().label("cnt"))
        .filter(Token.status == TokenStatus.completed)
        .group_by("hr")
        .order_by(func.count().desc())
        .first()
    )

    # Hourly distribution
    hourly = []
    for h in range(8, 18):
        label = f"{h}AM" if h < 12 else (f"{h - 12}PM" if h > 12 else "12PM")
        if h == 0:
            label = "12AM"
        cnt = db.query(func.count()).filter(func.strftime("%H", Token.issued_at) == f"{h:02d}").scalar()
        hourly.append({"hour": label, "count": cnt or 0})

    # Weekly trend from crowd counts
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekly = []
    for i, d in enumerate(days):
        cnt = (
            db.query(func.sum(CrowdCount.count))
            .filter(func.strftime("%w", CrowdCount.timestamp) == str(i + 1 if i < 6 else 0))
            .scalar()
        ) or 0
        weekly.append({"day": d, "crowd": cnt})

    busiest = max(weekly, key=lambda x: x["crowd"]) if weekly else {"day": "N/A", "crowd": 0}

    return AnalyticsOut(
        tokens_served=tokens_served,
        peak_time=f"{int(peak.hr)}:00" if peak else "N/A",
        peak_count=peak.cnt if peak else 0,
        avg_service_minutes=avg_svc,
        busiest_day=busiest["day"],
        busiest_day_count=busiest["crowd"],
        hourly_distribution=hourly,
        weekly_trend=weekly,
        completed_tokens=[TokenOut.model_validate(t) for t in completed],
    )

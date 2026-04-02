"""
Prophet-based crowd / token forecasting.
Trains on historical token issuance data and predicts future hourly demand.
"""

import logging
from datetime import datetime, timedelta

import pandas as pd
from prophet import Prophet
from sqlalchemy.orm import Session

from app.models import Token, CrowdCount

logger = logging.getLogger(__name__)

# Suppress Prophet's verbose stdout
logging.getLogger("prophet").setLevel(logging.WARNING)
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)


def _build_token_timeseries(db: Session) -> pd.DataFrame:
    """Build an hourly time-series from token issuance timestamps."""
    rows = db.query(Token.issued_at).all()
    if not rows:
        return pd.DataFrame(columns=["ds", "y"])

    df = pd.DataFrame([{"ds": r.issued_at} for r in rows])
    df["ds"] = pd.to_datetime(df["ds"])
    # Resample to hourly counts
    df = df.set_index("ds").resample("h").size().reset_index(name="y")
    return df


def _build_crowd_timeseries(db: Session) -> pd.DataFrame:
    """Build a time-series from crowd count logs."""
    rows = db.query(CrowdCount.timestamp, CrowdCount.count).all()
    if not rows:
        return pd.DataFrame(columns=["ds", "y"])

    df = pd.DataFrame([{"ds": r.timestamp, "y": r.count} for r in rows])
    df["ds"] = pd.to_datetime(df["ds"])
    df = df.sort_values("ds").reset_index(drop=True)
    return df


def forecast_hourly(db: Session, hours_ahead: int = 8, source: str = "tokens") -> list[dict]:
    """
    Use Prophet to forecast the next `hours_ahead` hours.

    Returns list of {"hour": "9AM", "predicted": 25, "actual": 14|None}
    """
    try:
        if source == "crowd":
            df = _build_crowd_timeseries(db)
        else:
            df = _build_token_timeseries(db)

        if len(df) < 3:
            # Not enough data – fall back to static predictions
            return _static_forecast(db)

        model = Prophet(
            daily_seasonality=True,
            weekly_seasonality=True,
            yearly_seasonality=False,
            changepoint_prior_scale=0.05,
        )
        model.fit(df)

        # Create future dataframe for today's remaining hours
        now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        start_hour = max(now.hour, 9)  # Operating hours start at 9
        future_hours = []
        for h in range(start_hour, start_hour + hours_ahead):
            dt = now.replace(hour=h % 24)
            future_hours.append(dt)

        future_df = pd.DataFrame({"ds": future_hours})
        forecast = model.predict(future_df)

        # Get actual counts for hours that have passed
        result = []
        for _, row in forecast.iterrows():
            hr = row["ds"].hour
            label = _hour_label(hr)
            predicted = max(0, int(round(row["yhat"])))

            # Check actual count for this hour
            actual = _get_actual_count(db, row["ds"], source)

            result.append({
                "hour": label,
                "predicted": predicted,
                "actual": actual,
                "yhat_lower": max(0, int(round(row["yhat_lower"]))),
                "yhat_upper": max(0, int(round(row["yhat_upper"]))),
            })

        return result

    except Exception as e:
        logger.warning(f"Prophet forecast failed: {e}. Using static fallback.")
        return _static_forecast(db)


def forecast_weekly(db: Session) -> list[dict]:
    """Forecast daily crowd for the next 7 days using Prophet."""
    try:
        df = _build_token_timeseries(db)

        if len(df) < 5:
            return _static_weekly()

        # Resample to daily
        df["ds"] = pd.to_datetime(df["ds"])
        daily = df.set_index("ds").resample("D").sum().reset_index()
        daily.columns = ["ds", "y"]

        if len(daily) < 3:
            return _static_weekly()

        model = Prophet(
            daily_seasonality=False,
            weekly_seasonality=True,
            yearly_seasonality=False,
        )
        model.fit(daily)

        future = model.make_future_dataframe(periods=7)
        forecast = model.predict(future)

        # Take last 7 days
        last_7 = forecast.tail(7)
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        result = []
        for _, row in last_7.iterrows():
            day_name = days[row["ds"].weekday()]
            result.append({
                "day": day_name,
                "crowd": max(0, int(round(row["yhat"]))),
                "lower": max(0, int(round(row["yhat_lower"]))),
                "upper": max(0, int(round(row["yhat_upper"]))),
            })

        return result

    except Exception as e:
        logger.warning(f"Prophet weekly forecast failed: {e}.")
        return _static_weekly()


def _get_actual_count(db: Session, dt: datetime, source: str) -> int | None:
    """Get actual count for a given hour. Returns None if the hour hasn't happened yet."""
    from sqlalchemy import func

    now = datetime.utcnow()
    if dt > now:
        return None

    hr_str = f"{dt.hour:02d}"

    if source == "crowd":
        count = (
            db.query(func.sum(CrowdCount.count))
            .filter(func.strftime("%H", CrowdCount.timestamp) == hr_str)
            .filter(func.date(CrowdCount.timestamp) == dt.date())
            .scalar()
        )
    else:
        count = (
            db.query(func.count())
            .filter(func.strftime("%H", Token.issued_at) == hr_str)
            .filter(func.date(Token.issued_at) == dt.date())
            .scalar()
        )

    return count if count and count > 0 else None


def _hour_label(h: int) -> str:
    if h == 0:
        return "12AM"
    elif h < 12:
        return f"{h}AM"
    elif h == 12:
        return "12PM"
    else:
        return f"{h - 12}PM"


def _static_forecast(db) -> list[dict]:
    """Hardcoded fallback when Prophet can't train."""
    from sqlalchemy import func

    hours = ["9AM", "10AM", "11AM", "12PM", "1PM", "2PM", "3PM", "4PM"]
    predicted = [12, 18, 25, 30, 28, 22, 19, 15]
    result = []
    for i, h in enumerate(hours):
        hr_24 = 9 + i if i < 4 else 13 + (i - 4)
        actual_count = (
            db.query(func.count())
            .filter(func.strftime("%H", Token.issued_at) == f"{hr_24:02d}")
            .scalar()
        )
        result.append({
            "hour": h,
            "predicted": predicted[i],
            "actual": actual_count if actual_count and actual_count > 0 else None,
        })
    return result


def _static_weekly() -> list[dict]:
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    counts = [120, 145, 132, 168, 155, 89, 42]
    return [{"day": d, "crowd": c} for d, c in zip(days, counts)]

from pydantic import BaseModel, EmailStr
from datetime import datetime


# ── Auth ──────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: str = "staff"


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ── Tokens ────────────────────────────────────────────

class TokenIssueRequest(BaseModel):
    customer_name: str | None = None


class ServeRequest(BaseModel):
    category: str
    estimated_minutes: int
    issue_description: str | None = None
    counter: int | None = None


class TokenOut(BaseModel):
    id: str
    token_number: str
    customer_name: str | None
    status: str
    category: str | None
    estimated_minutes: int | None
    issue_description: str | None
    counter: int | None
    service_time: float | None
    issued_at: datetime
    served_at: datetime | None
    completed_at: datetime | None

    class Config:
        from_attributes = True


class QueueStatusOut(BaseModel):
    position: int
    estimated_wait: int
    status: str
    counter: int | None = None


# ── Dashboard ─────────────────────────────────────────

class DashboardStats(BaseModel):
    live_count: int
    active_tokens: int
    avg_wait_minutes: float
    peak_hour: str


# ── Display ───────────────────────────────────────────

class NowServingOut(BaseModel):
    serving_token: str | None
    serving_counter: int | None
    upcoming_tokens: list[str]
    live_count: int


# ── Analytics ─────────────────────────────────────────

class HourlyItem(BaseModel):
    hour: str
    count: int


class WeeklyItem(BaseModel):
    day: str
    crowd: int


class AnalyticsOut(BaseModel):
    tokens_served: int
    peak_time: str
    peak_count: int
    avg_service_minutes: float
    busiest_day: str
    busiest_day_count: int
    hourly_distribution: list[HourlyItem]
    weekly_trend: list[WeeklyItem]
    completed_tokens: list[TokenOut]

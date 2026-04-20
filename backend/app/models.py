import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, Float, DateTime, Enum as SAEnum
from app.database import Base
import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    staff = "staff"
    customer = "customer"


class TokenStatus(str, enum.Enum):
    waiting = "waiting"
    serving = "serving"
    completed = "completed"
    cancelled = "cancelled"


class IssueCategory(str, enum.Enum):
    quick = "quick"
    standard = "standard"
    complex = "complex"
    custom = "custom"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False, index=True)
    full_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(SAEnum(UserRole), default=UserRole.staff, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Token(Base):
    __tablename__ = "tokens"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    token_number = Column(String, unique=True, nullable=False, index=True)
    customer_name = Column(String, nullable=True)
    customer_phone = Column(String, nullable=True)
    status = Column(SAEnum(TokenStatus), default=TokenStatus.waiting, nullable=False)
    category = Column(SAEnum(IssueCategory), nullable=True)
    estimated_minutes = Column(Integer, nullable=True)
    issue_description = Column(String, nullable=True)
    counter = Column(Integer, nullable=True)
    service_time = Column(Float, nullable=True)
    issued_at = Column(DateTime, default=datetime.utcnow)
    served_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class CrowdCount(Base):
    __tablename__ = "crowd_counts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    count = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings


_BACKEND_DIR = Path(__file__).resolve().parents[1]


def _parse_cors_origins(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    # Accept JSON-ish list, comma-separated, or single origin.
    v = value.strip()
    if v.startswith("[") and v.endswith("]"):
        v = v[1:-1]
    return [p.strip().strip('"').strip("'") for p in v.split(",") if p.strip()]


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./queue.db"
    SECRET_KEY: str = "change-me-in-production-use-a-random-secret"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Use an absolute default so the server can be started from any cwd.
    YOLO_MODEL_PATH: str = str(_BACKEND_DIR / "yolov8n.pt")

    # Set in Render to your Netlify origin(s). Example:
    # CORS_ORIGINS=https://your-site.netlify.app
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # Used for wait-time estimation. Set to total staffed counters in production.
    COUNTERS_COUNT: int = 1

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _validate_cors_origins(cls, v):
        return _parse_cors_origins(v)

    class Config:
        env_file = ".env"


settings = Settings()

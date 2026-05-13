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
    # For development: ["http://localhost:5173"]
    # For production deployment, use ["*"] to allow all origins or specify your frontend URL
    CORS_ORIGINS: list[str] = ["*"]

    # Used for wait-time estimation. Set to total staffed counters in production.
    COUNTERS_COUNT: int = 1

    # People counting backend: "hog" = OpenCV HOG (no PyTorch, reliable on Render free tier);
    # "ultralytics" = real YOLOv8; "demo" = trivial placeholder. UI can still say "YOLO".
    YOLO_MODE: str = "hog"

    @field_validator("YOLO_MODE", mode="before")
    @classmethod
    def _normalize_yolo_mode(cls, v):
        if v is None:
            return "hog"
        s = str(v).strip().lower()
        if s in ("ultralytics", "yolo", "torch", "real"):
            return "ultralytics"
        if s in ("demo", "mock", "fake"):
            return "demo"
        return "hog"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _validate_cors_origins(cls, v):
        return _parse_cors_origins(v)

    @field_validator("YOLO_MODEL_PATH", mode="after")
    @classmethod
    def _resolve_yolo_model_path(cls, v: str) -> str:
        # Render (and other hosts) may start the process with a cwd that is not `backend/`.
        # If YOLO_MODEL_PATH is relative (e.g. `yolov8n.pt`), anchor it to the backend package dir.
        p = Path(v)
        if not p.is_absolute():
            p = _BACKEND_DIR / p
        return str(p)

    class Config:
        env_file = ".env"


settings = Settings()

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite:///./queue.db"
    SECRET_KEY: str = "change-me-in-production-use-a-random-secret"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    YOLO_MODEL_PATH: str = "yolov8n.pt"
    CORS_ORIGINS: list[str] = ["http://localhost:8080", "http://localhost:5173", "*"]

    class Config:
        env_file = ".env"


settings = Settings()

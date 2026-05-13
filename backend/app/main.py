from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base
from app.routers import auth, tokens, dashboard, display, analytics, crowd

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Queue Management System", version="1.0.0")


def _cors_allowlist() -> tuple[list[str], bool]:
    """Starlette forbids allow_origins=['*'] with allow_credentials=True. Render env often
    lists only one origin and misses Netlify — merge known frontends."""
    raw = [o.rstrip("/") for o in settings.CORS_ORIGINS if o and str(o).strip()]
    if len(raw) == 1 and raw[0] == "*":
        return ["*"], False

    merged: list[str] = []
    seen: set[str] = set()
    for o in raw + [
        "https://steady-line.netlify.app",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]:
        if o not in seen:
            seen.add(o)
            merged.append(o)
    return merged, True


_cors_origins, _cors_credentials = _cors_allowlist()

# CORS - configured for production deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Length", "Content-Type"],
    max_age=600,  # Cache preflight requests for 10 minutes
)

# Mount routers under /api
app.include_router(auth.router, prefix="/api")
app.include_router(tokens.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(display.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(crowd.router, prefix="/api")


@app.get("/")
def root():
    return {"message": "AI Queue Management API", "docs": "/docs"}

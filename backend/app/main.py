import os

# Before heavy imports: less RAM / faster first paint on small hosts (Render)
os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base
from app.routers import auth, tokens, dashboard, display, analytics, crowd

# Create tables
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load YOLO off the request path so /health + /analyze don't race two downloads (OOM → no CORS headers).
    crowd.start_background_yolo_warm()
    yield


app = FastAPI(title="AI Queue Management System", version="1.0.0", lifespan=lifespan)


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

# Netlify production + deploy previews (regex); skip when using wildcard origins
_NETLIFY_ORIGIN_REGEX = r"https://([a-zA-Z0-9-]+--)?steady-line\.netlify\.app"

_cors_kw: dict = {
    "allow_origins": _cors_origins,
    "allow_credentials": _cors_credentials,
    "allow_methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    "allow_headers": ["*"],
    "expose_headers": ["Content-Length", "Content-Type"],
    "max_age": 600,
}
if _cors_origins != ["*"]:
    _cors_kw["allow_origin_regex"] = _NETLIFY_ORIGIN_REGEX

# CORS - configured for production deployment
app.add_middleware(
    CORSMiddleware,
    **_cors_kw,
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

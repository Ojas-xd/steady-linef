from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine, Base
from app.routers import auth, tokens, dashboard, display, analytics, crowd

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Queue Management System", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

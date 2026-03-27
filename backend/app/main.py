"""
EDAPT v2 — FastAPI Application Entry Point
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.session import engine
from app.db.base import Base
from app.api.routes import assessments, predictions, students, subjects


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create all DB tables on startup (dev convenience).
    Use Alembic migrations in production instead."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)
    yield
    await engine.dispose()


app = FastAPI(
    title="EDAPT v2 API",
    description="Educational Data Analytics and Predictive Tool — King's Own Institute",
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(students.router,     prefix="/api/v1/students",     tags=["Students"])
app.include_router(subjects.router,     prefix="/api/v1/subjects",      tags=["Subjects"])
app.include_router(assessments.router,  prefix="/api/v1/assessments",   tags=["Assessments"])
app.include_router(predictions.router,  prefix="/api/v1/predictions",   tags=["Predictions"])


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "version": "2.0.0"}

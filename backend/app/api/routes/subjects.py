"""EDAPT v2 — Subjects router (subject difficulty, class group stats)"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter()


@router.get("/")
async def list_subjects(db: AsyncSession = Depends(get_db)):
    """Return all subjects with average marks per trimester."""
    return {"message": "subjects endpoint — coming soon"}


@router.get("/{subject_code}/difficulty")
async def subject_difficulty(subject_code: str, db: AsyncSession = Depends(get_db)):
    """Return difficulty metrics (avg mark, pass rate) for a subject."""
    return {"subject_code": subject_code, "message": "difficulty endpoint — coming soon"}

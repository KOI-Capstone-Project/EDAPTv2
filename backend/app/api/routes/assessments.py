"""EDAPT v2 — Assessments router (Mode 1: historical performance)"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter()


@router.get("/")
async def list_assessments(
    trimester_id: int | None = Query(None, description="Filter by trimester"),
    subject_code: str | None = Query(None, description="Filter by subject code"),
    db: AsyncSession = Depends(get_db),
):
    """Return assessment records with optional filters."""
    return {"message": "assessments endpoint — coming soon"}


@router.get("/summary")
async def assessment_summary(
    trimester_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Aggregate marks by subject + trimester for the Mode 1 dashboard.
    Returns avg mark, pass rate, and weighting breakdown.
    """
    return {"message": "assessment summary — coming soon"}

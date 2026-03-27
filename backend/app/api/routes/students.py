"""EDAPT v2 — Students router (Mode 1: descriptive endpoints)"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter()


@router.get("/")
async def list_students(db: AsyncSession = Depends(get_db)):
    """Return a paginated list of anonymised student records."""
    # TODO: implement with SQLAlchemy select + pagination
    return {"message": "students endpoint — coming soon"}

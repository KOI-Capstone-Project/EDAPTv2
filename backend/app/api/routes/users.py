"""
EDAPT v2 — User management router.

All endpoints require the 'administrator' role.
Administrators can create, list, update, and deactivate user accounts
and assign roles (lecturer, hod, administrator).
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_roles
from app.core.security import hash_password
from app.db.models import User, UserRole
from app.db.session import get_db

router = APIRouter()

_ADMIN = UserRole.administrator.value
_VALID_ROLES = {r.value for r in UserRole}


# ── Schemas ───────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = UserRole.lecturer.value
    department: Optional[str] = None
    lecturer_id: Optional[int] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None
    lecturer_id: Optional[int] = None
    is_active: Optional[bool] = None


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    department: Optional[str]
    lecturer_id: Optional[int]
    is_active: bool
    last_login_at: Optional[datetime]

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _validate_role(role: str) -> None:
    if role not in _VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid role '{role}'. Valid options: {sorted(_VALID_ROLES)}.",
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[UserOut])
async def list_users(
    current_user: User = Depends(require_roles(_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Return all user accounts. Administrator only."""
    result = await db.execute(select(User).order_by(User.name))
    return result.scalars().all()


@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    current_user: User = Depends(require_roles(_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user account with a specified role. Administrator only."""
    _validate_role(payload.role)

    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists.",
        )

    user = User(
        name=payload.name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        department=payload.department,
        lecturer_id=payload.lecturer_id,
    )
    db.add(user)
    await db.flush()
    return user


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: int,
    current_user: User = Depends(require_roles(_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a single user by ID. Administrator only."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return user


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    current_user: User = Depends(require_roles(_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a user's role, department, lecturer link, name, or active status.
    Administrator only.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if payload.role is not None:
        _validate_role(payload.role)

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(user, field, value)

    await db.flush()
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: int,
    current_user: User = Depends(require_roles(_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """
    Deactivate a user account (sets is_active=False). Does not delete the record.
    Administrator only. Cannot deactivate your own account.
    """
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account.",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    user.is_active = False
    await db.flush()

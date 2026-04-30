"""
EDAPT v2 — Auth router
Endpoints: POST /register · POST /login · GET /me

/register is the bootstrap endpoint: it only works when no users exist in the
database yet, and it always creates an administrator account. Subsequent users
are created by an administrator via POST /api/v1/users.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.audit import append_event
from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User, UserRole
from app.db.session import get_db

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class BootstrapCreate(BaseModel):
    name: str
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    department: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(payload: BootstrapCreate, db: AsyncSession = Depends(get_db)):
    """
    Bootstrap endpoint — creates the first administrator account.

    Only succeeds when the users table is empty. Once any user exists,
    this endpoint returns 403. All further accounts must be created by
    an administrator via POST /api/v1/users.
    """
    count_result = await db.execute(select(func.count()).select_from(User))
    if count_result.scalar() > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Registration is disabled once users exist. "
                "Ask an administrator to create your account via POST /api/v1/users."
            ),
        )

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
        role=UserRole.administrator.value,
    )
    db.add(user)
    await db.flush()
    return user


@router.post("/login", response_model=TokenOut)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate with email + password; returns a JWT access token.

    FastAPI's OAuth2PasswordRequestForm reads ``username`` and ``password``
    from an application/x-www-form-urlencoded body — the frontend sends
    the email address in the ``username`` field.
    """
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(form.password, user.hashed_password):
        append_event(
            user_uid=form.username,
            role="Unknown",
            action_type="Login Failed",
            status="Alert",
            detail=f"Invalid credentials for {form.username}",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Contact an administrator.",
        )

    user.last_login_at = datetime.now(timezone.utc)

    append_event(
        user_uid=user.email,
        role=user.role,
        action_type="Login",
        status="Success",
        detail=f"Successful login for {user.email}",
    )
    token = create_access_token(subject=user.email)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    """Return the profile of the currently authenticated user."""
    return current_user

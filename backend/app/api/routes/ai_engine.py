"""
EDAPT v2 — AI Engine settings router.

Stores and retrieves the Gemini API key and selected model.
All endpoints require the 'administrator' role.
The API key is masked in GET responses — only a preview is returned.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import append_event
from app.core.deps import require_roles
from app.db.models import AppSettings, UserRole
from app.db.session import get_db

router = APIRouter()

_ADMIN = UserRole.administrator.value

KEY_GEMINI_API_KEY = "gemini_api_key"
KEY_GEMINI_MODEL   = "gemini_model"

VALID_MODELS = [
    "gemini-3",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
]
DEFAULT_MODEL = "gemini-2.5-flash"


# ── Schemas ───────────────────────────────────────────────────────────────────

class AIEngineIn(BaseModel):
    gemini_api_key: Optional[str] = None  # None = leave unchanged
    gemini_model: str = DEFAULT_MODEL


class AIEngineOut(BaseModel):
    gemini_api_key_set: bool
    gemini_api_key_preview: Optional[str] = None  # e.g. "AIzaSyAB..."
    gemini_model: str


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_setting(db: AsyncSession, key: str) -> Optional[str]:
    row = await db.get(AppSettings, key)
    return row.value if row else None


async def _set_setting(db: AsyncSession, key: str, value: str) -> None:
    row = await db.get(AppSettings, key)
    if row is None:
        db.add(AppSettings(key=key, value=value))
    else:
        row.value = value


def _mask_key(api_key: str) -> str:
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return api_key[:8] + "…"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=AIEngineOut)
async def get_ai_settings(
    current_user=Depends(require_roles(_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Return current AI engine configuration. API key is masked. Administrator only."""
    api_key = await _get_setting(db, KEY_GEMINI_API_KEY)
    model   = await _get_setting(db, KEY_GEMINI_MODEL) or DEFAULT_MODEL

    return AIEngineOut(
        gemini_api_key_set=bool(api_key),
        gemini_api_key_preview=_mask_key(api_key) if api_key else None,
        gemini_model=model,
    )


@router.put("/", response_model=AIEngineOut)
async def update_ai_settings(
    payload: AIEngineIn,
    current_user=Depends(require_roles(_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Save Gemini API key and/or model selection. Administrator only."""
    if payload.gemini_model not in VALID_MODELS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid model. Choose from: {VALID_MODELS}",
        )

    if payload.gemini_api_key is not None:
        stripped = payload.gemini_api_key.strip()
        if stripped:
            await _set_setting(db, KEY_GEMINI_API_KEY, stripped)

    await _set_setting(db, KEY_GEMINI_MODEL, payload.gemini_model)
    await db.flush()

    api_key = await _get_setting(db, KEY_GEMINI_API_KEY)
    key_action = "updated" if payload.gemini_api_key and payload.gemini_api_key.strip() else "unchanged"
    await append_event(
        user_uid=current_user.email,
        role=current_user.role,
        action_type="AI Engine Settings",
        status="Success",
        detail=f"Model set to '{payload.gemini_model}'; API key {key_action}",
    )
    return AIEngineOut(
        gemini_api_key_set=bool(api_key),
        gemini_api_key_preview=_mask_key(api_key) if api_key else None,
        gemini_model=payload.gemini_model,
    )

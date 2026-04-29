"""EDAPT v2 — Audit Log router"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api.routes.auth import get_current_user
from app.core.audit import _AUDIT_LOGS
from app.db.models import User

router = APIRouter()


@router.get("")
async def get_audit_logs(
    uid:          Optional[str] = Query(None),
    action_type:  Optional[str] = Query(None),
    status:       Optional[str] = Query(None),
    role:         Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    rows = list(_AUDIT_LOGS)
    if uid:
        rows = [r for r in rows if r["user_uid"] == uid]
    if action_type:
        rows = [r for r in rows if r["action_type"] == action_type]
    if status:
        rows = [r for r in rows if r["status"] == status]
    if role:
        rows = [r for r in rows if r.get("role") == role]
    return {"total": len(_AUDIT_LOGS), "count": len(rows), "data": rows}

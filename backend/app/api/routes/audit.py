"""EDAPT v2 — Audit Log router"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_roles
from app.db.models import AuditEvent, User, UserRole
from app.db.session import get_db

router = APIRouter()


@router.get("")
async def get_audit_logs(
    uid:         Optional[str] = Query(None, description="Filter by exact user email"),
    action_type: Optional[str] = Query(None, description="Filter by action type"),
    status:      Optional[str] = Query(None, description="Filter by status"),
    role:        Optional[str] = Query(None, description="Filter by role"),
    limit:       int           = Query(500, ge=1, le=2000, description="Max rows to return"),
    current_user: User = Depends(require_roles(UserRole.administrator.value)),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(limit)

    if uid:
        stmt = stmt.where(AuditEvent.user_uid == uid)
    if action_type:
        stmt = stmt.where(AuditEvent.action_type == action_type)
    if status:
        stmt = stmt.where(AuditEvent.status == status)
    if role:
        stmt = stmt.where(AuditEvent.role == role)

    result = await db.execute(stmt)
    events = result.scalars().all()

    total = await db.scalar(select(func.count()).select_from(AuditEvent))

    return {
        "total": total,
        "count": len(events),
        "data": [
            {
                "event_id":    f"EVT-{e.id:04d}",
                "timestamp":   e.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "user_uid":    e.user_uid,
                "role":        e.role or "",
                "action_type": e.action_type,
                "status":      e.status,
                "detail":      e.detail or "",
            }
            for e in events
        ],
    }

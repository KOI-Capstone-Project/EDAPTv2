"""
EDAPT v2 — Persistent audit logging.

append_event() opens its own dedicated DB session and commits immediately,
so audit records are preserved even when the originating request fails and
its main session rolls back (e.g. failed login attempts).
"""

from app.db.models import AuditEvent
from app.db.session import AsyncSessionLocal


async def append_event(
    *,
    user_uid: str,
    role: str,
    action_type: str,
    status: str,
    detail: str,
) -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(AuditEvent(
                user_uid=user_uid,
                role=role,
                action_type=action_type,
                status=status,
                detail=detail,
            ))

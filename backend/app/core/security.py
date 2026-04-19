"""
EDAPT v2 — Security Utilities
Password hashing (bcrypt) + JWT creation / verification.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# ── Password hashing ──────────────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches *hashed*."""
    return pwd_context.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────────────────────
ALGORITHM = "HS256"


def create_access_token(
    subject: Any,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create a signed JWT.

    Args:
        subject: Typically the user's email or integer ID.
        expires_delta: Custom expiry window; defaults to ACCESS_TOKEN_EXPIRE_MINUTES.

    Returns:
        Encoded JWT string.
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {"sub": str(subject), "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """
    Decode and verify a JWT.

    Returns:
        The ``sub`` claim (user identifier) if valid, otherwise None.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None

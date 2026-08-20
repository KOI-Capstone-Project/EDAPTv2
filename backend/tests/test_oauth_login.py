"""EDAPT v2 — Google / Microsoft OAuth sign-in.

We never call the real Google/Microsoft endpoints in tests (no network,
no real client credentials). `verify_google_id_token` / `verify_microsoft_id_token`
are mocked to stand in for "the provider verified this token and it belongs
to this email" — everything downstream of that (the invite-only account
lookup, JWT issuance) is real and exercised end to end.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import oauth_providers
from app.main import app


@pytest.mark.asyncio
async def test_google_login_rejected_when_client_id_not_configured():
    # No GOOGLE_CLIENT_ID is set in the test environment, so verification
    # itself should refuse to run rather than silently trusting the token.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/auth/google", json={"id_token": "whatever"})
    assert response.status_code == 401
    assert "not configured" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_microsoft_login_rejected_when_client_id_not_configured():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/auth/microsoft", json={"id_token": "whatever"})
    assert response.status_code == 401
    assert "not configured" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_google_login_succeeds_for_a_preexisting_account():
    # "admin" is one of the seeded default accounts (see _seed_default_users).
    with patch.object(oauth_providers, "verify_google_id_token", return_value="admin"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/auth/google", json={"id_token": "fake-but-verified"})
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "admin"
    assert body["user"]["role"] == "Head of Technology"
    assert "access_token" in body


@pytest.mark.asyncio
async def test_microsoft_login_succeeds_for_a_preexisting_account():
    with patch.object(
        oauth_providers, "verify_microsoft_id_token", new=AsyncMock(return_value="user")
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/auth/microsoft", json={"id_token": "fake-but-verified"})
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "user"
    assert body["user"]["role"] == "Lecturer"


@pytest.mark.asyncio
async def test_oauth_login_rejected_for_email_with_no_edapt_account():
    # Invite-only model: a real, verified provider identity is not enough —
    # an admin must have already created a matching EDAPT user account.
    with patch.object(
        oauth_providers, "verify_google_id_token", return_value="nobody@example.com"
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/auth/google", json={"id_token": "fake-but-verified"})
    assert response.status_code == 403
    assert "no edapt account" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_oauth_login_rejected_for_deactivated_account(async_session_factory=None):
    # Reuse the same deactivation path password login already enforces —
    # OAuth must not be a backdoor around a disabled account.
    from sqlalchemy import select

    from app.db.models import User as UserModel
    from app.main import _AsyncSession

    async with _AsyncSession() as db:
        result = await db.execute(select(UserModel).where(UserModel.email == "hos"))
        db_user = result.scalar_one()
        was_active = db_user.is_active
        db_user.is_active = False
        await db.commit()

    try:
        with patch.object(oauth_providers, "verify_google_id_token", return_value="hos"):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/api/auth/google", json={"id_token": "fake-but-verified"})
        assert response.status_code == 403
        assert "deactivated" in response.json()["detail"].lower()
    finally:
        async with _AsyncSession() as db:
            result = await db.execute(select(UserModel).where(UserModel.email == "hos"))
            db_user = result.scalar_one()
            db_user.is_active = was_active
            await db.commit()

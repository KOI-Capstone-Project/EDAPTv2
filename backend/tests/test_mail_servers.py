"""
EDAPT v2 — Settings > Outgoing Mail Servers (multiple admin-managed SMTP
servers, modeled on Odoo's ir.mail_server — see MailServer's docstring in
app/db/models.py).

Covers a real bug caught during manual testing: reading row.updated_at
straight off the ORM object right after `await db.commit()` — without an
explicit `await db.refresh(row)` in between — crashed with a 500
(SQLAlchemy's implicit lazy-reload on an expired, server-computed column
isn't awaitable in this async context). Fixed by refreshing the row before
building the response, the same commit-then-refresh pairing already used
for AnalyzeJob/IngestJob elsewhere in this file. test_update_mail_server
below is the regression test for that exact crash.
"""

import contextlib

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete, select

import app.main as main_mod
from app.db.models import MailServer
from app.main import app


async def _login(client, email: str, password: str) -> str:
    res = await client.post("/api/auth/login", json={"email": email, "password": password})
    return res.json()["access_token"]


@contextlib.asynccontextmanager
async def _preserve_mail_servers():
    """Snapshot + restore the mail_servers table around a test — a shared,
    cross-worker Postgres table a stray test write would pollute for the
    real app too (same reasoning as _preserve_ai_config in
    test_ai_config.py)."""
    async with main_mod._AsyncSession() as db:
        existing_ids = (await db.execute(select(MailServer.id))).scalars().all()
    try:
        yield
    finally:
        async with main_mod._AsyncSession() as db:
            await db.execute(delete(MailServer).where(MailServer.id.notin_(existing_ids)))
            await db.commit()


@pytest.mark.asyncio
async def test_create_list_and_get_never_return_plaintext_password():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        async with _preserve_mail_servers():
            r = await client.post(
                "/api/mail-servers", headers=headers,
                json={
                    "name": "Test SMTP", "host": "smtp.example.com", "port": 587,
                    "security": "starttls", "username": "bot@example.com",
                    "password": "super-secret-app-password", "from_email": "bot@example.com",
                    "priority": 10, "active": True,
                },
            )
            assert r.status_code == 201, r.text
            body = r.json()
            assert body["has_password"] is True
            assert "password" not in body
            assert "super-secret-app-password" not in str(body)

            listing = (await client.get("/api/mail-servers", headers=headers)).json()
            assert any(s["id"] == body["id"] for s in listing["servers"])
            assert "super-secret-app-password" not in str(listing)


@pytest.mark.asyncio
async def test_update_mail_server():
    """Regression test for the confirmed post-commit-refresh crash — see
    this file's module docstring."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        async with _preserve_mail_servers():
            create = await client.post(
                "/api/mail-servers", headers=headers,
                json={
                    "name": "Original Name", "host": "smtp.example.com", "port": 587,
                    "security": "starttls", "username": "bot@example.com",
                    "password": "initial-password", "priority": 10, "active": True,
                },
            )
            server_id = create.json()["id"]

            # Blank password on update — must keep the existing one, not wipe it.
            r = await client.put(
                f"/api/mail-servers/{server_id}", headers=headers,
                json={
                    "name": "Renamed", "host": "smtp.example.com", "port": 465,
                    "security": "ssl", "username": "bot@example.com",
                    "priority": 5, "active": True,
                },
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["name"] == "Renamed"
            assert body["port"] == 465
            assert body["security"] == "ssl"
            assert body["priority"] == 5
            assert body["has_password"] is True
            assert body["updated_by"] == "admin"
            assert body["updated_at"]


@pytest.mark.asyncio
async def test_delete_mail_server():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        async with _preserve_mail_servers():
            create = await client.post(
                "/api/mail-servers", headers=headers,
                json={"name": "To Delete", "host": "smtp.example.com", "port": 587, "security": "none"},
            )
            server_id = create.json()["id"]

            r = await client.delete(f"/api/mail-servers/{server_id}", headers=headers)
            assert r.status_code == 200
            assert r.json() == {"deleted": True}

            listing = (await client.get("/api/mail-servers", headers=headers)).json()
            assert all(s["id"] != server_id for s in listing["servers"])

            r_missing = await client.delete(f"/api/mail-servers/{server_id}", headers=headers)
            assert r_missing.status_code == 404


@pytest.mark.asyncio
async def test_mail_server_endpoints_reject_lecturer():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        login = await client.post("/api/auth/login", json={"email": "user", "password": "Lect@2025!"})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        assert (await client.get("/api/mail-servers", headers=headers)).status_code == 403
        assert (await client.post(
            "/api/mail-servers", headers=headers,
            json={"name": "x", "host": "smtp.example.com", "port": 587},
        )).status_code == 403
        assert (await client.post(
            "/api/mail-servers/test", headers=headers,
            json={"host": "smtp.example.com", "port": 587},
        )).status_code == 403


@pytest.mark.asyncio
async def test_create_rejects_invalid_security():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.post(
            "/api/mail-servers", headers=headers,
            json={"name": "x", "host": "smtp.example.com", "port": 587, "security": "not-a-real-option"},
        )
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_test_connection_fails_fast_for_unreachable_host():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.post(
            "/api/mail-servers/test", headers=headers,
            json={"host": "smtp.invalid.nonexistent.example", "port": 587, "security": "starttls"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is False
        assert "message" in body and body["message"]
        assert "elapsed_seconds" in body


@pytest.mark.asyncio
async def test_test_connection_requires_host_and_port_or_server_id():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.post("/api/mail-servers/test", headers=headers, json={})
        assert r.status_code == 422


@pytest.mark.asyncio
async def test_test_connection_rejects_unknown_server_id():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.post("/api/mail-servers/test", headers=headers, json={"server_id": 999999})
        assert r.status_code == 404

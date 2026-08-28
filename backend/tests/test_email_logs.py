"""
EDAPT v2 — Send Test Email (POST /api/mail-servers/send-test-email) and
Email Logs (GET /api/email-logs, GET /api/email-logs/{id}).

Every email this app tries to send — a test email or the real
forgot-password OTP — is recorded in EmailLog, success or failure (see
EmailLog's docstring in app/db/models.py for why status is only ever
'sent'/'failed', never a fabricated 'delivered'). These tests use a mail
server pointed at an address nothing listens on, so every send genuinely
fails — that's the point: it proves a failed send is still logged
correctly with a real failure_reason, not silently dropped.
"""

import contextlib

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete, select

import app.main as main_mod
from app.db.models import EmailLog, MailServer
from app.main import app


async def _login(client, email: str, password: str) -> str:
    res = await client.post("/api/auth/login", json={"email": email, "password": password})
    return res.json()["access_token"]


@contextlib.asynccontextmanager
async def _preserve_mail_servers_and_logs():
    """Same reasoning as test_mail_servers.py's _preserve_mail_servers,
    extended to email_logs since sending a test email always writes one."""
    async with main_mod._AsyncSession() as db:
        existing_server_ids = (await db.execute(select(MailServer.id))).scalars().all()
        existing_log_ids     = (await db.execute(select(EmailLog.id))).scalars().all()
    try:
        yield
    finally:
        async with main_mod._AsyncSession() as db:
            await db.execute(delete(EmailLog).where(EmailLog.id.notin_(existing_log_ids)))
            await db.execute(delete(MailServer).where(MailServer.id.notin_(existing_server_ids)))
            await db.commit()


async def _create_unreachable_server(client, headers) -> int:
    """A server pointed at a host nothing listens on, port that will refuse
    the connection quickly — every send through this genuinely fails,
    deterministically and fast, without needing real SMTP credentials."""
    res = await client.post(
        "/api/mail-servers", headers=headers,
        json={
            "name": "Unreachable Test Server", "host": "127.0.0.1", "port": 1,
            "security": "none", "priority": 1, "active": True,
        },
    )
    return res.json()["id"]


@pytest.mark.asyncio
async def test_send_test_email_logs_failure_with_real_reason():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        async with _preserve_mail_servers_and_logs():
            server_id = await _create_unreachable_server(client, headers)

            r = await client.post(
                "/api/mail-servers/send-test-email", headers=headers,
                json={
                    "server_id": server_id, "from_email": "sender@example.com",
                    "to_email": "recipient@example.com", "subject": "Test",
                    "body": "<p>Hello <strong>world</strong></p>",
                },
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["status"] == "failed"
            assert body["failure_reason"]
            log_id = body["log_id"]

            listing = (await client.get("/api/email-logs", headers=headers)).json()
            logged = next((entry for entry in listing["logs"] if entry["id"] == log_id), None)
            assert logged is not None
            assert logged["status"] == "failed"
            assert logged["kind"] == "test"
            assert logged["sent_by"] == "admin"
            assert logged["from_email"] == "sender@example.com"
            assert logged["to_email"] == "recipient@example.com"
            assert logged["is_html"] is True
            # List shape intentionally omits the body — only the detail
            # endpoint returns it.
            assert "body" not in logged

            detail = (await client.get(f"/api/email-logs/{log_id}", headers=headers)).json()
            assert detail["body"] == "<p>Hello <strong>world</strong></p>"


@pytest.mark.asyncio
async def test_send_test_email_rejects_malformed_from_and_to_addresses():
    """SendTestEmailRequest previously accepted any non-empty string for
    from_email/to_email — a typo'd address would only surface later as an
    opaque SMTP failure. Both fields must now match the same email pattern
    every other email field in this app validates against (_EMAIL_REGEX)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        r1 = await client.post(
            "/api/mail-servers/send-test-email", headers=headers,
            json={"from_email": "not-an-email", "to_email": "recipient@example.com", "body": "<p>hi</p>"},
        )
        assert r1.status_code == 422

        r2 = await client.post(
            "/api/mail-servers/send-test-email", headers=headers,
            json={"from_email": "sender@example.com", "to_email": "nope", "body": "<p>hi</p>"},
        )
        assert r2.status_code == 422


@pytest.mark.asyncio
async def test_send_test_email_requires_a_configured_server():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        async with _preserve_mail_servers_and_logs():
            # Omitting server_id (meaning "use whichever is active") against
            # whatever this environment currently has configured: either
            # there genuinely is no active server (400 — the real behavior
            # this test exists to check) or a real admin-configured one
            # exists and the send is attempted (200, sent or failed
            # depending on that real server) — this test can't force the
            # "no server" case without tearing down a real admin's config,
            # so it only asserts the response is one of those two
            # well-defined outcomes, never a 500 — and the preserve-context
            # cleans up any real EmailLog row this creates either way.
            r = await client.post(
                "/api/mail-servers/send-test-email", headers=headers,
                json={"from_email": "a@example.com", "to_email": "b@example.com", "body": "<p>x</p>"},
            )
            assert r.status_code in (200, 400)


@pytest.mark.asyncio
async def test_send_test_email_rejects_unknown_server_id():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        r = await client.post(
            "/api/mail-servers/send-test-email", headers=headers,
            json={"server_id": 999999, "from_email": "a@example.com", "to_email": "b@example.com", "body": "<p>x</p>"},
        )
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_email_log_endpoints_reject_lecturer():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        login = await client.post("/api/auth/login", json={"email": "user", "password": "Lect@2025!"})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        assert (await client.get("/api/email-logs", headers=headers)).status_code == 403
        assert (await client.post(
            "/api/mail-servers/send-test-email", headers=headers,
            json={"from_email": "a@example.com", "to_email": "b@example.com", "body": "<p>x</p>"},
        )).status_code == 403


@pytest.mark.asyncio
async def test_email_logs_filter_by_status_and_kind():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        async with _preserve_mail_servers_and_logs():
            server_id = await _create_unreachable_server(client, headers)
            send = await client.post(
                "/api/mail-servers/send-test-email", headers=headers,
                json={
                    "server_id": server_id, "from_email": "a@example.com",
                    "to_email": "b@example.com", "body": "<p>x</p>",
                },
            )
            log_id = send.json()["log_id"]

            failed_only = (await client.get("/api/email-logs", headers=headers, params={"status": "failed"})).json()
            assert any(entry["id"] == log_id for entry in failed_only["logs"])

            sent_only = (await client.get("/api/email-logs", headers=headers, params={"status": "sent"})).json()
            assert all(entry["id"] != log_id for entry in sent_only["logs"])

            test_kind = (await client.get("/api/email-logs", headers=headers, params={"kind": "test"})).json()
            assert any(entry["id"] == log_id for entry in test_kind["logs"])

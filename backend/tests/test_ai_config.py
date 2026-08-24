"""EDAPT v2 — Settings > AI Config (GET/PUT /api/ai-config).

Covers the switch from a single hardcoded GEMINI_API_KEY env var to a
DB-backed, admin-editable provider/model/key: the real key is never
returned in plaintext (only has_key + a masked preview), a blank api_key
on PUT keeps whatever's already stored (so switching models doesn't force
re-entering the same key), and only known provider/model combinations are
accepted.
"""

import contextlib

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete

import app.main as main_mod
from app.db.models import AIProviderConfig
from app.main import app


async def _login(client, email: str, password: str) -> str:
    res = await client.post("/api/auth/login", json={"email": email, "password": password})
    return res.json()["access_token"]


@contextlib.asynccontextmanager
async def _preserve_ai_config():
    """Snapshot the singleton config row and restore it afterward, and
    refresh the in-memory cache both times — a shared, cross-worker
    Postgres row a stray test write would pollute for the real app too,
    and _AI_CONFIG_CACHE would otherwise keep serving the test's values
    to any real AI call made after this test in the same process."""
    async with main_mod._AsyncSession() as db:
        row = await db.get(AIProviderConfig, 1)
        original = None if row is None else {
            "provider": row.provider, "model": row.model, "encrypted_api_key": row.encrypted_api_key,
        }
    try:
        yield
    finally:
        async with main_mod._AsyncSession() as db:
            row = await db.get(AIProviderConfig, 1)
            if original is None:
                if row is not None:
                    await db.execute(delete(AIProviderConfig))
            elif row is not None:
                row.provider, row.model, row.encrypted_api_key = (
                    original["provider"], original["model"], original["encrypted_api_key"],
                )
            await db.commit()
        await main_mod._refresh_ai_config_cache()


@pytest.mark.asyncio
async def test_get_ai_config_never_returns_plaintext_key():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.get("/api/ai-config", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert "provider" in body and "model" in body and "has_key" in body
    assert "api_key" not in body
    assert set(body["available_models"].keys()) == {"anthropic", "gemini", "openai"}


@pytest.mark.asyncio
async def test_get_ai_config_rejects_lecturer():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "user", "Lect@2025!")
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.get("/api/ai-config", headers=headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_update_ai_config_persists_and_masks_key():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await _login(client, "admin", "Admin@2025!")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        lect_token = await _login(client, "user", "Lect@2025!")
        lect_headers = {"Authorization": f"Bearer {lect_token}"}

        async with _preserve_ai_config():
            r_forbidden = await client.put(
                "/api/ai-config", headers=lect_headers,
                json={"provider": "openai", "model": "gpt-4o", "api_key": "nope"},
            )
            assert r_forbidden.status_code == 403

            r = await client.put(
                "/api/ai-config", headers=admin_headers,
                json={"provider": "openai", "model": "gpt-5.5", "api_key": "sk-test-abcd1234"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["provider"] == "openai"
            assert body["model"] == "gpt-5.5"
            assert body["has_key"] is True
            assert body["key_preview"] == "••••1234"
            assert "sk-test-abcd1234" not in str(body)
            assert body["updated_by"] == "admin"

            r_get = await client.get("/api/ai-config", headers=admin_headers)
            assert r_get.json()["provider"] == "openai"
            assert r_get.json()["model"] == "gpt-5.5"


@pytest.mark.asyncio
async def test_update_ai_config_blank_key_keeps_existing_one():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        async with _preserve_ai_config():
            await client.put(
                "/api/ai-config", headers=headers,
                json={"provider": "gemini", "model": "gemini-3.1-pro-preview", "api_key": "AIzaTestKey1111"},
            )
            # Switch model only, no api_key in the request — the key set
            # above must survive, not be wiped.
            r = await client.put(
                "/api/ai-config", headers=headers,
                json={"provider": "gemini", "model": "gemini-3.7-flash"},
            )
            assert r.status_code == 200
            assert r.json()["has_key"] is True
            assert r.json()["key_preview"] == "••••1111"
            assert r.json()["model"] == "gemini-3.7-flash"


@pytest.mark.asyncio
async def test_update_ai_config_rejects_unknown_provider_and_model():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        async with _preserve_ai_config():
            r_bad_provider = await client.put(
                "/api/ai-config", headers=headers,
                json={"provider": "not-a-provider", "model": "whatever"},
            )
            assert r_bad_provider.status_code == 422

            r_bad_model = await client.put(
                "/api/ai-config", headers=headers,
                json={"provider": "gemini", "model": "not-a-real-model"},
            )
            assert r_bad_model.status_code == 422

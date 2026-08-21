"""EDAPT v2 — Settings > OAuth Providers config (GET/PUT /api/oauth-providers,
GET /api/oauth-providers/public).

Covers the switch from GOOGLE_CLIENT_ID/MICROSOFT_CLIENT_ID/MICROSOFT_TENANT_ID
env vars to a DB-backed, admin-editable config: both providers always list
(even before anyone has configured them), only an admin can write to them,
and the public endpoint only ever exposes enabled providers with a client_id.
"""

import contextlib

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete

import app.main as main_mod
from app.db.models import OAuthProviderConfig
from app.main import app


async def _login(client, email: str, password: str) -> str:
    res = await client.post("/api/auth/login", json={"email": email, "password": password})
    return res.json()["access_token"]


@contextlib.asynccontextmanager
async def _preserve_oauth_provider_configs():
    """Snapshot both provider rows and restore them afterward — a shared,
    cross-worker Postgres table a stray test write would pollute for the
    real app too."""
    async with main_mod._AsyncSession() as db:
        originals = {}
        for provider in ("google", "microsoft"):
            row = await db.get(OAuthProviderConfig, provider)
            originals[provider] = None if row is None else {
                "client_id": row.client_id, "tenant_id": row.tenant_id, "enabled": row.enabled,
            }
    try:
        yield
    finally:
        async with main_mod._AsyncSession() as db:
            for provider, snap in originals.items():
                row = await db.get(OAuthProviderConfig, provider)
                if snap is None:
                    if row is not None:
                        await db.execute(delete(OAuthProviderConfig).where(OAuthProviderConfig.provider == provider))
                elif row is not None:
                    row.client_id, row.tenant_id, row.enabled = snap["client_id"], snap["tenant_id"], snap["enabled"]
            await db.commit()


@pytest.mark.asyncio
async def test_list_oauth_providers_always_shows_google_and_microsoft():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.get("/api/oauth-providers", headers=headers)
    assert r.status_code == 200
    providers = {p["provider"] for p in r.json()["providers"]}
    assert providers == {"google", "microsoft"}


@pytest.mark.asyncio
async def test_list_oauth_providers_rejects_lecturer():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "user", "Lect@2025!")
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.get("/api/oauth-providers", headers=headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_update_oauth_provider_admin_only_and_persists():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await _login(client, "admin", "Admin@2025!")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        lect_token = await _login(client, "user", "Lect@2025!")
        lect_headers = {"Authorization": f"Bearer {lect_token}"}

        async with _preserve_oauth_provider_configs():
            r_forbidden = await client.put(
                "/api/oauth-providers/google", headers=lect_headers,
                json={"client_id": "nope", "enabled": True},
            )
            assert r_forbidden.status_code == 403

            r = await client.put(
                "/api/oauth-providers/microsoft", headers=admin_headers,
                json={"client_id": "test-ms-client-id", "tenant_id": "test-tenant", "enabled": True},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["client_id"] == "test-ms-client-id"
            assert body["tenant_id"] == "test-tenant"
            assert body["enabled"] is True
            assert body["updated_by"] == "admin"

            r_get = await client.get("/api/oauth-providers", headers=admin_headers)
            ms = next(p for p in r_get.json()["providers"] if p["provider"] == "microsoft")
            assert ms["client_id"] == "test-ms-client-id"
            assert ms["enabled"] is True

            # Public endpoint should now expose it too, since it's enabled with a client_id.
            r_public = await client.get("/api/oauth-providers/public")
            public_ms = next((p for p in r_public.json()["providers"] if p["provider"] == "microsoft"), None)
            assert public_ms is not None
            assert public_ms["client_id"] == "test-ms-client-id"


@pytest.mark.asyncio
async def test_update_oauth_provider_cannot_enable_without_client_id():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await _login(client, "admin", "Admin@2025!")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        async with _preserve_oauth_provider_configs():
            r = await client.put(
                "/api/oauth-providers/google", headers=admin_headers,
                json={"client_id": "", "enabled": True},
            )
            assert r.status_code == 200
            # enabled=True was requested but there's no client_id to verify tokens against.
            assert r.json()["enabled"] is False


@pytest.mark.asyncio
async def test_update_oauth_provider_rejects_unknown_provider():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.put(
            "/api/oauth-providers/facebook", headers=headers,
            json={"client_id": "x", "enabled": True},
        )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_public_oauth_providers_excludes_disabled():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await _login(client, "admin", "Admin@2025!")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        async with _preserve_oauth_provider_configs():
            await client.put(
                "/api/oauth-providers/google", headers=admin_headers,
                json={"client_id": "some-client-id", "enabled": False},
            )
            r_public = await client.get("/api/oauth-providers/public")
            providers = {p["provider"] for p in r_public.json()["providers"]}
            assert "google" not in providers

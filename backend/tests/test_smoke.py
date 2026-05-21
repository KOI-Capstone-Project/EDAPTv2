"""EDAPT v2 — Smoke tests for the FastAPI app."""

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_login_success():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/auth/login",
            json={"email": "admin", "password": "Admin@2025!"},
        )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "token_type" in body


@pytest.mark.asyncio
async def test_login_wrong_password():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/auth/login",
            json={"email": "admin", "password": "definitely_wrong_password"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_brute_force():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(6):
            response = await client.post(
                "/api/auth/login",
                json={"email": "bruteforce@smoke.test", "password": "wrong"},
            )
    assert response.status_code == 429


@pytest.mark.asyncio
async def test_predict_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/predict",
            json={"subject": "ICT104", "assess1_mark": 50.0},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ingest_preview_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/ingest/preview")
    assert response.status_code == 401

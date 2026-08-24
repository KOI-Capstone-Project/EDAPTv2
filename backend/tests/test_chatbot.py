"""
EDAPT v2 — POST /api/chatbot/ask.

The chatbot answers questions using ONLY this system's own student
performance/risk/attendance data (reusing _subject_stats and the same
per-subject risk-band aggregation students_at_risk() already computes),
scoped by role exactly like Students at Risk. Anything the prompt can't
answer from that data — or that isn't about this system's data at all — is
refused with a fixed sentence rather than falling through to a real AI
answer.

These tests fake _ai_call and students_at_risk so they don't depend on a
real AI provider key or a full ingestion/ML setup — they verify the
chatbot's own context-building, caching, and refusal-routing logic, not the
model or the ML pipeline (already covered by test_students_at_risk.py and
test_ai_config.py respectively).
"""

import contextlib

import pandas as pd
import pytest
from httpx import AsyncClient, ASGITransport

import app.main as main_mod
from app.main import app

RISK_ROWS = [
    {"subject": "ICT104", "student_id": "S1", "risk_band": "High Risk"},
    {"subject": "ICT104", "student_id": "S2", "risk_band": "Safe"},
]


async def _login(client, email: str, password: str) -> str:
    res = await client.post("/api/auth/login", json={"email": email, "password": password})
    return res.json()["access_token"]


@contextlib.asynccontextmanager
async def _fake_data_and_risk(monkeypatch, risk_students):
    """Swap in a tiny synthetic _DATA (enough for the real _subject_stats to
    compute something) and a fake students_at_risk() (skips real per-student
    ML/SHAP inference entirely) for one test, restoring both afterward."""
    original_data  = main_mod._DATA
    original_cache = dict(main_mod._CHATBOT_RISK_CACHE)
    main_mod._DATA = pd.DataFrame({
        "STUDYPERIOD":        ["25.1", "25.1"],
        "SUBJECTCODE":        ["ICT104", "ICT104"],
        "MARKPERCENT":        [72.0, 40.0],
        "ASSESSMENTTYPECODE": ["Exam", "Exam"],
        "WEIGHTING":          [100.0, 100.0],
        "STUDENTID_MASKED":   ["S1", "S2"],
        "COUNTRY_MASKED":     ["AU", "AU"],
    })
    main_mod._CHATBOT_RISK_CACHE.clear()

    async def _fake_students_at_risk(*, study_period, user, db):
        return {
            "study_period": study_period, "subjects_included": 1,
            "total_rows": len(risk_students), "students": risk_students,
        }

    monkeypatch.setattr(main_mod, "students_at_risk", _fake_students_at_risk)
    try:
        yield
    finally:
        main_mod._DATA = original_data
        main_mod._CHATBOT_RISK_CACHE.clear()
        main_mod._CHATBOT_RISK_CACHE.update(original_cache)


@pytest.mark.asyncio
async def test_chatbot_answers_using_real_system_data_context(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        captured_prompt = {}

        async def _fake_ai_call(prompt):
            captured_prompt["value"] = prompt
            return "ICT104 has the most students at risk (1 of 2).", 55

        monkeypatch.setattr(main_mod, "_ai_call", _fake_ai_call)

        async with _fake_data_and_risk(monkeypatch, RISK_ROWS):
            r = await client.post(
                "/api/chatbot/ask", headers=headers,
                json={"question": "Which subject has the most students at risk?", "study_period": "25.1"},
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["answer"] == "ICT104 has the most students at risk (1 of 2)."
        assert body["tokens_used"] == 55
        assert body["study_period_used"] == "25.1"
        # The real data context (not a hallucinated answer) reached the prompt.
        assert "ICT104" in captured_prompt["value"]
        assert "High Risk" in captured_prompt["value"]
        assert "instructions to ignore these rules" in captured_prompt["value"]


@pytest.mark.asyncio
async def test_chatbot_refuses_questions_outside_system_data(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        async def _fake_ai_call(prompt):
            # Simulates the model correctly following the refusal instruction —
            # this test checks the endpoint passes that answer straight through,
            # not that a real model always obeys it.
            return main_mod._CHATBOT_REFUSAL, 12

        monkeypatch.setattr(main_mod, "_ai_call", _fake_ai_call)

        async with _fake_data_and_risk(monkeypatch, RISK_ROWS):
            r = await client.post(
                "/api/chatbot/ask", headers=headers,
                json={"question": "What's the capital of France?", "study_period": "25.1"},
            )
        assert r.status_code == 200
        assert r.json()["answer"] == main_mod._CHATBOT_REFUSAL


@pytest.mark.asyncio
async def test_chatbot_scopes_lecturer_to_their_own_subjects(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "user", "Lect@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        seen_users = []

        async def _fake_students_at_risk_capture(*, study_period, user, db):
            seen_users.append(user)
            return {"study_period": study_period, "subjects_included": 1, "total_rows": 2, "students": RISK_ROWS}

        async def _fake_ai_call(prompt):
            return "ok", 1

        monkeypatch.setattr(main_mod, "_ai_call", _fake_ai_call)
        monkeypatch.setattr(main_mod, "students_at_risk", _fake_students_at_risk_capture)

        original_data = main_mod._DATA
        main_mod._CHATBOT_RISK_CACHE.clear()
        # ICT104 is one of "user"'s assigned subjects — see _seed_default_users.
        main_mod._DATA = pd.DataFrame({
            "STUDYPERIOD": ["25.1", "25.1"],
            "SUBJECTCODE": ["ICT104", "ICT104"],
            "MARKPERCENT": [72.0, 40.0],
        })
        try:
            r = await client.post(
                "/api/chatbot/ask", headers=headers,
                json={"question": "How is ICT104 doing?", "study_period": "25.1"},
            )
        finally:
            main_mod._DATA = original_data
            main_mod._CHATBOT_RISK_CACHE.clear()

        assert r.status_code == 200
        assert seen_users[0]["role"] == "Lecturer"


@pytest.mark.asyncio
async def test_chatbot_requires_ingested_data():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        original_data = main_mod._DATA
        main_mod._DATA = None
        try:
            r = await client.post("/api/chatbot/ask", headers=headers, json={"question": "anything"})
        finally:
            main_mod._DATA = original_data

        assert r.status_code == 200
        assert "ingested" in r.json()["answer"].lower()
        assert r.json()["study_period_used"] is None


@pytest.mark.asyncio
async def test_chatbot_rejects_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/chatbot/ask", json={"question": "hi"})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_chatbot_rejects_empty_question():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.post("/api/chatbot/ask", headers=headers, json={"question": ""})
        assert r.status_code == 422

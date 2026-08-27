"""
EDAPT v2 — POST /api/chatbot/ask.

The chatbot answers questions using ONLY this system's own student
performance/risk/attendance data: _subject_stats() for raw-marks context,
plus per-subject risk-band counts read directly off the Predictions table
(NOT recomputed via subject_roster()/students_at_risk() — that re-runs real
per-student ML/SHAP inference across every visible subject and was
confirmed to take 50s+ end-to-end on the full dataset, far too slow for an
interactive chat reply). Scoped by role exactly like Students at Risk.
Anything the prompt can't answer from that data — or that isn't about this
system's data at all — is refused with a fixed sentence rather than
falling through to a real AI answer.

These tests seed real Prediction rows under a synthetic study period
("99.9"/"99.8") that no real ingested data ever uses, so they exercise the
actual DB aggregation (dedup across model versions, role scoping, the
honest "nothing scored yet" case) without needing a full ingestion/ML
pipeline. _ai_call is faked so these tests don't depend on a real AI
provider key.
"""

import contextlib

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete

import app.main as main_mod
from app.db.models import Prediction
from app.main import app

TEST_PERIOD       = "99.9"  # synthetic — never a real ingested period
EMPTY_TEST_PERIOD = "99.8"  # synthetic — always zero Prediction rows


async def _login(client, email: str, password: str) -> str:
    res = await client.post("/api/auth/login", json={"email": email, "password": password})
    return res.json()["access_token"]


async def _seed_prediction(db, *, student_id, subject, risk_band, model_version="test-v1"):
    db.add(Prediction(
        student_id_masked=student_id, subject_code=subject, study_period=TEST_PERIOD,
        model_version=model_version,
        predicted_pass=(risk_band != "High Risk"),
        pass_probability=0.9 if risk_band == "Safe" else 0.2,
        risk_band=risk_band,
    ))
    await db.commit()


@contextlib.asynccontextmanager
async def _cleanup_test_predictions():
    try:
        yield
    finally:
        async with main_mod._AsyncSession() as db:
            await db.execute(delete(Prediction).where(Prediction.study_period.in_([TEST_PERIOD, EMPTY_TEST_PERIOD])))
            await db.commit()


@pytest.mark.asyncio
async def test_chatbot_answers_using_real_predictions_table_context(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        async with _cleanup_test_predictions():
            async with main_mod._AsyncSession() as db:
                await _seed_prediction(db, student_id="ChatS1", subject="ICT104", risk_band="High Risk")
                await _seed_prediction(db, student_id="ChatS2", subject="ICT104", risk_band="Safe")

            captured_prompt = {}

            async def _fake_ai_call(prompt):
                captured_prompt["value"] = prompt
                return "ICT104 has the most students at risk (1 of 2).", 55

            monkeypatch.setattr(main_mod, "_ai_call", _fake_ai_call)

            r = await client.post(
                "/api/chatbot/ask", headers=headers,
                json={"question": "Which subject has the most students at risk?", "study_period": TEST_PERIOD},
            )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["answer"] == "ICT104 has the most students at risk (1 of 2)."
        assert body["tokens_used"] == 55
        assert body["study_period_used"] == TEST_PERIOD
        assert "ICT104" in captured_prompt["value"]
        assert "High Risk" in captured_prompt["value"]
        assert "greeting" in captured_prompt["value"].lower()


@pytest.mark.asyncio
async def test_chatbot_dedups_across_model_versions_to_latest_only(monkeypatch):
    """One student re-predicted under a newer model version must count once,
    as their MOST RECENT risk band — not once per historical row."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        async with _cleanup_test_predictions():
            async with main_mod._AsyncSession() as db:
                # Older model version: this student was High Risk...
                await _seed_prediction(db, student_id="ChatS3", subject="ICT104", risk_band="High Risk", model_version="v1")
            async with main_mod._AsyncSession() as db:
                # ...then re-predicted under a newer model version as Safe.
                await _seed_prediction(db, student_id="ChatS3", subject="ICT104", risk_band="Safe", model_version="v2")

            captured_prompt = {}

            async def _fake_ai_call(prompt):
                captured_prompt["value"] = prompt
                return "ok", 1

            monkeypatch.setattr(main_mod, "_ai_call", _fake_ai_call)

            r = await client.post(
                "/api/chatbot/ask", headers=headers,
                json={"question": "How many students are at risk in ICT104?", "study_period": TEST_PERIOD},
            )
        assert r.status_code == 200
        # Only the latest (Safe) row should be reflected — one enrolment, not two.
        assert '"total_scored_enrolments": 1' in captured_prompt["value"]
        assert '"safe": 1' in captured_prompt["value"]
        assert '"high_risk": 1' not in captured_prompt["value"]


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

        r = await client.post(
            "/api/chatbot/ask", headers=headers,
            json={"question": "What's the capital of France?"},
        )
        assert r.status_code == 200
        assert r.json()["answer"] == main_mod._CHATBOT_REFUSAL


@pytest.mark.asyncio
async def test_chatbot_scopes_lecturer_to_their_own_subjects(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "user", "Lect@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        async with _cleanup_test_predictions():
            async with main_mod._AsyncSession() as db:
                # ICT104 is one of "user"'s assigned subjects (see _seed_default_users);
                # ICT999 deliberately is not.
                await _seed_prediction(db, student_id="ChatS4", subject="ICT104", risk_band="High Risk")
                await _seed_prediction(db, student_id="ChatS5", subject="ICT999", risk_band="High Risk")

            captured_prompt = {}

            async def _fake_ai_call(prompt):
                captured_prompt["value"] = prompt
                return "ok", 1

            monkeypatch.setattr(main_mod, "_ai_call", _fake_ai_call)

            r = await client.post(
                "/api/chatbot/ask", headers=headers,
                json={"question": "How are my subjects doing?", "study_period": TEST_PERIOD},
            )
        assert r.status_code == 200
        assert "ICT104" in captured_prompt["value"]
        assert "ICT999" not in captured_prompt["value"]


@pytest.mark.asyncio
async def test_chatbot_reports_no_predictions_computed_yet_honestly(monkeypatch):
    """A period with zero Predictions rows must be reported as 'nothing
    scored yet', never silently rendered as zero-at-risk-students (a real
    and very different fact)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        captured_prompt = {}

        async def _fake_ai_call(prompt):
            captured_prompt["value"] = prompt
            return "ok", 1

        monkeypatch.setattr(main_mod, "_ai_call", _fake_ai_call)

        r = await client.post(
            "/api/chatbot/ask", headers=headers,
            json={"question": "How many students are at risk?", "study_period": EMPTY_TEST_PERIOD},
        )
        assert r.status_code == 200
        assert "No risk predictions have been computed" in captured_prompt["value"]


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

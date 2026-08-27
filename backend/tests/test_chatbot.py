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

Also covers the later additions to the context the chatbot builds:
per-subject attendance + an attendance/outcome correlation, an
all-visible-subjects performance table for subject-vs-subject comparison,
already-logged intervention counts, a named-student lookup against that
student's own Prediction rows, and when the live dataset was last
ingested. The attendance/comparison tests monkeypatch main_mod._ATTENDANCE/
_DATA with a small synthetic dataframe (restored in a finally block) since
those two context pieces read the real in-memory dataset directly rather
than a DB table a synthetic study period can isolate into.
"""

import contextlib
from datetime import datetime, timezone

import pandas as pd
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete

import app.main as main_mod
from app.db.models import IngestJob, Intervention, Prediction
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


async def _seed_intervention(db, *, student_id, subject, action_type):
    db.add(Intervention(
        student_id_masked=student_id, subject_code=subject, study_period=TEST_PERIOD,
        action_type=action_type, created_by="admin",
    ))
    await db.commit()


@contextlib.asynccontextmanager
async def _cleanup_test_interventions():
    try:
        yield
    finally:
        async with main_mod._AsyncSession() as db:
            await db.execute(delete(Intervention).where(Intervention.study_period == TEST_PERIOD))
            await db.commit()


@pytest.mark.asyncio
async def test_chatbot_reports_already_logged_interventions(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        async with _cleanup_test_interventions():
            async with main_mod._AsyncSession() as db:
                await _seed_intervention(db, student_id="ChatI1", subject="ICT104", action_type="email sent")
                await _seed_intervention(db, student_id="ChatI2", subject="ICT104", action_type="email sent")

            captured_prompt = {}

            async def _fake_ai_call(prompt):
                captured_prompt["value"] = prompt
                return "ok", 1

            monkeypatch.setattr(main_mod, "_ai_call", _fake_ai_call)

            r = await client.post(
                "/api/chatbot/ask", headers=headers,
                json={"question": "Have we already emailed at-risk students in ICT104?", "study_period": TEST_PERIOD},
            )
        assert r.status_code == 200
        assert '"total_logged": 2' in captured_prompt["value"]
        assert '"subject": "ICT104"' in captured_prompt["value"]
        assert '"action_type": "email sent"' in captured_prompt["value"]


@pytest.mark.asyncio
async def test_chatbot_reports_no_interventions_honestly(monkeypatch):
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
            json={"question": "Has anyone been contacted?", "study_period": EMPTY_TEST_PERIOD},
        )
        assert r.status_code == 200
        assert "No interventions" in captured_prompt["value"]


def _synthetic_marks_df(rows):
    """Minimal columns _chatbot_subject_comparison / _role_filter need."""
    return pd.DataFrame(rows, columns=["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD", "MARKPERCENT"])


@pytest.mark.asyncio
async def test_chatbot_subject_comparison_covers_every_visible_subject(monkeypatch):
    """A lecturer's subject list is always small, so every one of their
    subjects should appear in subject_comparison — not just the worst-N,
    the capping that only applies to an admin's much larger visible set."""
    synthetic = _synthetic_marks_df([
        ("CmpS1", "ICT104", TEST_PERIOD, 90.0), ("CmpS2", "ICT104", TEST_PERIOD, 80.0),
        ("CmpS3", "ICT201", TEST_PERIOD, 40.0), ("CmpS4", "ICT201", TEST_PERIOD, 30.0),
    ])
    original_data = main_mod._DATA
    main_mod._DATA = synthetic
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client, "user", "Lect@2025!")  # subjects: ICT104, ICT201, ICT301
            headers = {"Authorization": f"Bearer {token}"}

            captured_prompt = {}

            async def _fake_ai_call(prompt):
                captured_prompt["value"] = prompt
                return "ok", 1

            monkeypatch.setattr(main_mod, "_ai_call", _fake_ai_call)

            r = await client.post(
                "/api/chatbot/ask", headers=headers,
                json={"question": "Compare ICT104 and ICT201", "study_period": TEST_PERIOD},
            )
        assert r.status_code == 200
        prompt = captured_prompt["value"]
        assert '"subject": "ICT104"' in prompt and '"avg_mark": 85.0' in prompt
        assert '"subject": "ICT201"' in prompt and '"avg_mark": 35.0' in prompt
        assert '"difficulty": "Low"' in prompt   # ICT104: 0% fail rate
        assert '"difficulty": "High"' in prompt  # ICT201: 100% fail rate
    finally:
        main_mod._DATA = original_data


def _synthetic_attendance_df(rows):
    return pd.DataFrame(rows, columns=["SUBJECTCODE", "STUDYPERIOD", "ATTENDANCE_RATE", "PASS"])


@pytest.mark.asyncio
async def test_chatbot_reports_attendance_and_correlation(monkeypatch):
    # Perfectly correlated toy data: high attendance -> pass, low -> fail,
    # so the sign/rough magnitude of the correlation is unambiguous to assert on.
    synthetic = _synthetic_attendance_df([
        ("ICT104", TEST_PERIOD, 0.95, 1), ("ICT104", TEST_PERIOD, 0.90, 1),
        ("ICT104", TEST_PERIOD, 0.20, 0), ("ICT104", TEST_PERIOD, 0.15, 0),
    ])
    original_attendance = main_mod._ATTENDANCE
    main_mod._ATTENDANCE = synthetic
    try:
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
                json={"question": "Is attendance linked to passing?", "study_period": TEST_PERIOD},
            )
        assert r.status_code == 200
        prompt = captured_prompt["value"]
        assert '"has_attendance_data": true' in prompt
        assert '"overall_avg_attendance_rate": 55.0' in prompt
        assert '"attendance_pass_correlation": 0.9' in prompt  # strongly positive, not exactly checked to 3dp
    finally:
        main_mod._ATTENDANCE = original_attendance


@pytest.mark.asyncio
async def test_chatbot_student_lookup_found_and_not_found(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        async with _cleanup_test_predictions():
            async with main_mod._AsyncSession() as db:
                await _seed_prediction(db, student_id="Student777777", subject="ICT104", risk_band="At Risk")

            captured_prompt = {}

            async def _fake_ai_call(prompt):
                captured_prompt["value"] = prompt
                return "ok", 1

            monkeypatch.setattr(main_mod, "_ai_call", _fake_ai_call)

            # Found: the question names a student who has a real prediction row.
            r = await client.post(
                "/api/chatbot/ask", headers=headers,
                json={"question": "How is Student777777 doing?", "study_period": TEST_PERIOD},
            )
            assert r.status_code == 200
            prompt = captured_prompt["value"]
            assert '"student_lookup"' in prompt
            assert '"student_id": "Student777777"' in prompt
            assert '"found": true' in prompt
            assert '"risk_band": "At Risk"' in prompt

            # Not found: a well-formed but nonexistent student id.
            r2 = await client.post(
                "/api/chatbot/ask", headers=headers,
                json={"question": "How is Student000000 doing?", "study_period": TEST_PERIOD},
            )
            assert r2.status_code == 200
            prompt2 = captured_prompt["value"]
            assert '"student_id": "Student000000"' in prompt2
            assert '"found": false' in prompt2

        # A question naming no student at all must not add student_lookup.
        r3 = await client.post(
            "/api/chatbot/ask", headers=headers,
            json={"question": "What's the overall pass rate?", "study_period": TEST_PERIOD},
        )
        assert r3.status_code == 200
        assert '"student_lookup"' not in captured_prompt["value"]


@pytest.mark.asyncio
async def test_chatbot_student_lookup_tolerates_a_space_before_the_number(monkeypatch):
    """Real bug, confirmed live: "student 20035193" (a space — the natural
    way most people type it) previously fell straight through
    _STUDENT_ID_PATTERN's zero-width \\bStudent\\d+\\b, so student_lookup
    was silently never added and the model fell back to a flat
    "outside this system's data" refusal for what was actually an
    in-scope, just-unresolvable student question. Also checks the
    reconstructed id is the no-space canonical form ("Student777777"),
    not whatever spacing the user happened to type."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        async with _cleanup_test_predictions():
            async with main_mod._AsyncSession() as db:
                await _seed_prediction(db, student_id="Student777777", subject="ICT104", risk_band="At Risk")

            captured_prompt = {}

            async def _fake_ai_call(prompt):
                captured_prompt["value"] = prompt
                return "ok", 1

            monkeypatch.setattr(main_mod, "_ai_call", _fake_ai_call)

            r = await client.post(
                "/api/chatbot/ask", headers=headers,
                json={"question": "How is student 777777 doing?", "study_period": TEST_PERIOD},
            )
            assert r.status_code == 200
            prompt = captured_prompt["value"]
            assert '"student_lookup"' in prompt
            assert '"student_id": "Student777777"' in prompt
            assert '"found": true' in prompt


@pytest.mark.asyncio
async def test_chatbot_student_lookup_falls_back_to_conversation_history(monkeypatch):
    """Real bug, confirmed live: after "How is Student4912 doing?", a
    pronoun follow-up like "is he enrolled in just this one subject?"
    names no student itself, so student_lookup was never added for that
    turn and the model fell back to the flat refusal even though the
    conversation clearly established who "he" is. Falls back to the most
    recent student id mentioned in the client-echoed history when the
    current question has none."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        async with _cleanup_test_predictions():
            async with main_mod._AsyncSession() as db:
                await _seed_prediction(db, student_id="Student777777", subject="ICT104", risk_band="At Risk")

            captured_prompt = {}

            async def _fake_ai_call(prompt):
                captured_prompt["value"] = prompt
                return "ok", 1

            monkeypatch.setattr(main_mod, "_ai_call", _fake_ai_call)

            r = await client.post(
                "/api/chatbot/ask", headers=headers,
                json={
                    "question": "is he enrolled in just this one subject?",
                    "study_period": TEST_PERIOD,
                    "history": [
                        {"role": "user", "content": "How is Student777777 doing?"},
                        {"role": "assistant", "content": "Student777777 is enrolled in ICT104..."},
                    ],
                },
            )
            assert r.status_code == 200
            prompt = captured_prompt["value"]
            assert '"student_lookup"' in prompt
            assert '"student_id": "Student777777"' in prompt
            assert '"found": true' in prompt

        # No student ever mentioned, in this question or history: no lookup.
        r2 = await client.post(
            "/api/chatbot/ask", headers=headers,
            json={
                "question": "is he passing?",
                "study_period": TEST_PERIOD,
                "history": [{"role": "user", "content": "what's the overall pass rate?"}],
            },
        )
        assert r2.status_code == 200
        assert '"student_lookup"' not in captured_prompt["value"]


@pytest.mark.asyncio
async def test_chatbot_bare_number_with_no_student_word_is_not_treated_as_a_student_id(monkeypatch):
    """A number with no "student" anywhere in the question (a real
    institutional id, a mark, a year) is deliberately NOT resolved to a
    student lookup — this system's masked ids only ever look like
    "Student<N>", and guessing on every number-bearing question would be
    worse than occasionally missing an unlabeled reference. This is the
    one part of the reported "20035193" case that's expected behavior, not
    a bug: that number was never a valid masked id in this dataset's
    format regardless of how the question was phrased."""
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
            json={"question": "How is 20035193 doing?", "study_period": TEST_PERIOD},
        )
        assert r.status_code == 200
        assert '"student_lookup"' not in captured_prompt["value"]


@pytest.mark.asyncio
async def test_chatbot_reports_data_freshness(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}

        job = None
        async with main_mod._AsyncSession() as db:
            job = IngestJob(
                kind="capstone", status="success", started_by="test",
                finished_at=datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc),
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)

        try:
            captured_prompt = {}

            async def _fake_ai_call(prompt):
                captured_prompt["value"] = prompt
                return "ok", 1

            monkeypatch.setattr(main_mod, "_ai_call", _fake_ai_call)

            r = await client.post(
                "/api/chatbot/ask", headers=headers,
                json={"question": "How current is this data?", "study_period": TEST_PERIOD},
            )
            assert r.status_code == 200
            assert "2026-01-15" in captured_prompt["value"]
        finally:
            async with main_mod._AsyncSession() as db:
                await db.execute(delete(IngestJob).where(IngestJob.id == job.id))
                await db.commit()

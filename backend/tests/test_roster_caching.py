"""
EDAPT v2 — subject_roster()'s prediction cache.

Real gap this closes: subject_roster() used to unconditionally rerun the
full ML+SHAP inference for every student on every single call, regardless
of what was already sitting in the `predictions` table — so a background
bulk-scoring pass (ScoringJob) could pre-populate that table and Predictor/
Students at Risk would still recompute from scratch every time someone
opened them. _compute_roster_rows now checks for a fresh cached Prediction
first (see _fresh_cached_prediction's docstring in app/main.py) and only
falls back to a real model call when no fresh one exists.

These tests isolate that cache-check logic with a small synthetic _DATA
dataframe and a directly-seeded Prediction row — not the real trained model
— by monkeypatching app.ml.predictor.predict to raise if it's ever called
(proving a cache hit truly skips it) or to return a distinguishable fake
result (proving a cache miss truly recomputes). _live_model_version and
_latest_successful_ingest_at are also monkeypatched so freshness is
deterministic and doesn't depend on which model happens to be live or what
ingestion history exists in this dev database.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from httpx import AsyncClient, ASGITransport

import app.main as main_mod
from app.db.models import Prediction
from app.main import app

TEST_SUBJECT = "CACHE100"  # synthetic — never a real ingested subject
TEST_PERIOD  = "99.9"      # synthetic — never a real ingested period
LIVE_MODEL_VERSION = "test-live-v1"


def _synthetic_complete_df():
    """One student, 100% coverage (two assessments, 50% weighting each) —
    lands squarely in the 'complete' coverage tier (>=99.5%), matching the
    real live model's own decision path."""
    return pd.DataFrame([
        {
            "STUDENTID_MASKED": "CacheStudent1", "SUBJECTCODE": TEST_SUBJECT,
            "STUDYPERIOD": TEST_PERIOD, "MARKPERCENT": 80.0, "WEIGHTING": 50.0,
            "ASSESSMENTTYPECODE": "Assignment", "STUDYPACKAGEASSESSMENTID": 1,
        },
        {
            "STUDENTID_MASKED": "CacheStudent1", "SUBJECTCODE": TEST_SUBJECT,
            "STUDYPERIOD": TEST_PERIOD, "MARKPERCENT": 70.0, "WEIGHTING": 50.0,
            "ASSESSMENTTYPECODE": "Exam", "STUDYPACKAGEASSESSMENTID": 2,
        },
    ])


async def _seed_prediction(*, model_version: str, predicted_at: datetime) -> None:
    async with main_mod._AsyncSession() as db:
        db.add(Prediction(
            student_id_masked="CacheStudent1", subject_code=TEST_SUBJECT, study_period=TEST_PERIOD,
            model_version=model_version, predicted_pass=True, pass_probability=0.87,
            risk_band="Safe", estimate_type=None, predicted_at=predicted_at,
            top_actionable_factor={"feature": "CACHED_FEATURE", "value": 1.0,
                                    "contribution": -1.0, "direction": "Fail"},
        ))
        await db.commit()


async def _cleanup():
    async with main_mod._AsyncSession() as db:
        from sqlalchemy import delete
        await db.execute(delete(Prediction).where(Prediction.study_period == TEST_PERIOD))
        await db.commit()


async def _login(client) -> str:
    res = await client.post("/api/auth/login", json={"email": "admin", "password": "Admin@2025!"})
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_roster_reuses_a_fresh_cached_prediction_without_calling_the_model(monkeypatch):
    """A Prediction row that matches the live model_version and was computed
    after the latest ingestion must be reused as-is — ml_predict must NEVER
    be called for that student. Proven by making ml_predict raise if it is."""
    original_data = main_mod._DATA
    original_reliability = main_mod._SUBJECT_RELIABILITY
    main_mod._DATA = _synthetic_complete_df()
    main_mod._SUBJECT_RELIABILITY = {"fully_clean": [TEST_SUBJECT], "mostly_clean": []}

    async def fake_live_version(family):
        return LIVE_MODEL_VERSION

    async def fake_cutoff(db):
        return datetime.now(timezone.utc) - timedelta(days=1)

    def boom(*args, **kwargs):
        raise AssertionError("ml_predict must not be called on a fresh cache hit")

    monkeypatch.setattr(main_mod, "_live_model_version", fake_live_version)
    monkeypatch.setattr(main_mod, "_latest_successful_ingest_at", fake_cutoff)
    monkeypatch.setattr("app.ml.predictor.predict", boom)
    monkeypatch.setattr("app.ml.predictor.predict_partial", boom)

    try:
        await _cleanup()
        await _seed_prediction(
            model_version=LIVE_MODEL_VERSION,
            predicted_at=datetime.now(timezone.utc),  # after the cutoff above -> fresh
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client)
            r = await client.get(
                "/api/subjects/{}/roster".format(TEST_SUBJECT), headers={"Authorization": f"Bearer {token}"},
                params={"study_period": TEST_PERIOD},
            )
        assert r.status_code == 200, r.text
        row = r.json()["roster"][0]
        assert row["risk_band"] == "Safe"
        assert row["probability"] == 87.0
        assert row["top_actionable_factor"] == {
            "feature": "CACHED_FEATURE", "value": 1.0, "contribution": -1.0, "direction": "Fail",
        }
    finally:
        main_mod._DATA = original_data
        main_mod._SUBJECT_RELIABILITY = original_reliability
        await _cleanup()


@pytest.mark.asyncio
async def test_roster_recomputes_when_the_cached_prediction_is_from_a_superseded_model(monkeypatch):
    """A Prediction row whose model_version no longer matches the currently
    live model must be treated as stale — the real model call must happen,
    and the roster must reflect the FRESH result, not the stale cached one."""
    original_data = main_mod._DATA
    original_reliability = main_mod._SUBJECT_RELIABILITY
    main_mod._DATA = _synthetic_complete_df()
    main_mod._SUBJECT_RELIABILITY = {"fully_clean": [TEST_SUBJECT], "mostly_clean": []}

    async def fake_live_version(family):
        return LIVE_MODEL_VERSION

    async def fake_cutoff(db):
        return datetime.now(timezone.utc) - timedelta(days=1)

    called = {"value": False}

    def fake_predict(**kwargs):
        called["value"] = True
        return {
            "probability": 42.0, "prediction": "Fail", "risk_band": "High Risk",
            "model_version": LIVE_MODEL_VERSION, "attendance_rate_used": None,
            "shap_explanation": None,
        }

    monkeypatch.setattr(main_mod, "_live_model_version", fake_live_version)
    monkeypatch.setattr(main_mod, "_latest_successful_ingest_at", fake_cutoff)
    monkeypatch.setattr("app.ml.predictor.predict", fake_predict)

    try:
        await _cleanup()
        await _seed_prediction(
            model_version="an-old-superseded-version",  # != LIVE_MODEL_VERSION above
            predicted_at=datetime.now(timezone.utc),
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client)
            r = await client.get(
                "/api/subjects/{}/roster".format(TEST_SUBJECT), headers={"Authorization": f"Bearer {token}"},
                params={"study_period": TEST_PERIOD},
            )
        assert r.status_code == 200, r.text
        assert called["value"] is True, "a stale-model-version cached row must not be reused"
        row = r.json()["roster"][0]
        assert row["risk_band"] == "High Risk"
        assert row["probability"] == 42.0
    finally:
        main_mod._DATA = original_data
        main_mod._SUBJECT_RELIABILITY = original_reliability
        await _cleanup()


@pytest.mark.asyncio
async def test_roster_recomputes_when_the_cached_prediction_predates_the_latest_ingestion(monkeypatch):
    """A Prediction row with the right model_version but computed BEFORE the
    latest successful ingestion must also be treated as stale — the
    student's own underlying data may have changed since. Real model call
    must happen."""
    original_data = main_mod._DATA
    original_reliability = main_mod._SUBJECT_RELIABILITY
    main_mod._DATA = _synthetic_complete_df()
    main_mod._SUBJECT_RELIABILITY = {"fully_clean": [TEST_SUBJECT], "mostly_clean": []}

    async def fake_live_version(family):
        return LIVE_MODEL_VERSION

    async def fake_cutoff(db):
        # Cutoff is AFTER the seeded prediction's predicted_at below.
        return datetime.now(timezone.utc) + timedelta(minutes=5)

    called = {"value": False}

    def fake_predict(**kwargs):
        called["value"] = True
        return {
            "probability": 10.0, "prediction": "Fail", "risk_band": "High Risk",
            "model_version": LIVE_MODEL_VERSION, "attendance_rate_used": None,
            "shap_explanation": None,
        }

    monkeypatch.setattr(main_mod, "_live_model_version", fake_live_version)
    monkeypatch.setattr(main_mod, "_latest_successful_ingest_at", fake_cutoff)
    monkeypatch.setattr("app.ml.predictor.predict", fake_predict)

    try:
        await _cleanup()
        await _seed_prediction(
            model_version=LIVE_MODEL_VERSION,
            predicted_at=datetime.now(timezone.utc) - timedelta(hours=1),  # before the cutoff -> stale
        )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client)
            r = await client.get(
                "/api/subjects/{}/roster".format(TEST_SUBJECT), headers={"Authorization": f"Bearer {token}"},
                params={"study_period": TEST_PERIOD},
            )
        assert r.status_code == 200, r.text
        assert called["value"] is True, "a prediction older than the latest ingestion must not be reused"
        assert r.json()["roster"][0]["risk_band"] == "High Risk"
    finally:
        main_mod._DATA = original_data
        main_mod._SUBJECT_RELIABILITY = original_reliability
        await _cleanup()

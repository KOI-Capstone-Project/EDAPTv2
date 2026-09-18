"""
EDAPT v2 — GET /api/dashboard/summary's "Total At Risk" / "At Risk" KPI.

Real gap this closes: the KPI used to count distinct students with AT LEAST
ONE assessment ITEM scored below 50%, ever, across their whole multi-year,
multi-subject history — not "currently failing" or "predicted to fail" in
any meaningful sense. Reported live: this read as ~88% of the whole cohort
"at risk" sitting right next to an 82% institution pass rate, which looked
like a contradiction but was really two metrics answering unrelated
questions (a per-item raw-marks count vs. a per-item raw-marks average).
With several years of history per student, almost everyone has one weak
item somewhere — the number was real but close to meaningless, and
alarming purely as an artifact of its own definition.

Fixed to reuse the same real ML risk_band predictions already computed by
the scoring engine and already shown on Students at Risk / used by the
chatbot — so this headline dashboard KPI cannot disagree with either of
those, and genuinely reflects "predicted at risk of failing" rather than
"once had a bad day on one assignment."

These tests seed a small synthetic _DATA dataframe (never a real ingested
subject/period) plus directly-seeded Prediction rows, so they don't depend
on the real trained model or real ingested data — same technique
test_roster_caching.py already uses.
"""
from datetime import datetime, timezone

import pandas as pd
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete

import app.main as main_mod
from app.db.models import Prediction
from app.main import app

TEST_SUBJECT  = "ATRISK01"  # synthetic — never a real ingested subject
TEST_SUBJECT2 = "ATRISK02"
TEST_PERIOD   = "97.7"      # synthetic — never a real ingested period


def _synthetic_df():
    """Three students in TEST_SUBJECT, each with a low mark on record —
    deliberately so a raw-marks reading would flag all three, proving the
    KPI is genuinely reading risk_band and not just re-deriving from marks."""
    return pd.DataFrame([
        {
            "STUDENTID_MASKED": sid, "SUBJECTCODE": TEST_SUBJECT, "STUDYPERIOD": TEST_PERIOD,
            "MARKPERCENT": 40.0, "WEIGHTING": 100.0,
            "ASSESSMENTTYPECODE": "Exam", "STUDYPACKAGEASSESSMENTID": i,
        }
        for i, sid in enumerate(["AtRiskStudentSafe", "AtRiskStudentAtRisk", "AtRiskStudentHigh"])
    ])


async def _seed_prediction(*, student: str, subject: str, risk_band: str, predicted_at=None) -> None:
    async with main_mod._AsyncSession() as db:
        db.add(Prediction(
            student_id_masked=student, subject_code=subject, study_period=TEST_PERIOD,
            model_version="test-v1", predicted_pass=(risk_band == "Safe"),
            pass_probability=0.9 if risk_band == "Safe" else 0.2,
            risk_band=risk_band, estimate_type=None,
            predicted_at=predicted_at or datetime.now(timezone.utc),
        ))
        await db.commit()


async def _cleanup():
    async with main_mod._AsyncSession() as db:
        await db.execute(delete(Prediction).where(Prediction.study_period == TEST_PERIOD))
        await db.commit()


async def _login(client) -> str:
    res = await client.post("/api/auth/login", json={"email": "admin", "password": "Admin@2025!"})
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_at_risk_count_reflects_real_predicted_risk_bands_not_raw_marks():
    """All three synthetic students have the SAME low raw mark (40%) — a
    raw-marks-based count would flag all three. Only the two whose real
    prediction says "At Risk"/"High Risk" must be counted; the one
    predicted "Safe" must not, proving this reads risk_band, not marks."""
    original_data = main_mod._DATA
    main_mod._DATA = _synthetic_df()
    try:
        await _cleanup()
        await _seed_prediction(student="AtRiskStudentSafe",   subject=TEST_SUBJECT, risk_band="Safe")
        await _seed_prediction(student="AtRiskStudentAtRisk", subject=TEST_SUBJECT, risk_band="At Risk")
        await _seed_prediction(student="AtRiskStudentHigh",   subject=TEST_SUBJECT, risk_band="High Risk")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client)
            res = await client.get(
                "/api/dashboard/summary", headers={"Authorization": f"Bearer {token}"},
                params={"trimester": TEST_PERIOD},
            )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["total_students"] == 3
        assert body["at_risk_count"] == 2, \
            "must count the At-Risk/High-Risk predictions only, not all 3 low-raw-mark students"
    finally:
        main_mod._DATA = original_data
        await _cleanup()


@pytest.mark.asyncio
async def test_at_risk_count_is_none_when_nothing_in_scope_has_been_scored_yet():
    """Real data exists (3 students, low marks) but zero Prediction rows —
    a genuine "haven't scored this yet" gap. Must report None, never a
    fabricated 0 that would misleadingly read as "nobody's at risk"."""
    original_data = main_mod._DATA
    main_mod._DATA = _synthetic_df()
    try:
        await _cleanup()  # ensure no leftover predictions from another test

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client)
            res = await client.get(
                "/api/dashboard/summary", headers={"Authorization": f"Bearer {token}"},
                params={"trimester": TEST_PERIOD},
            )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["total_students"] == 3, "real ingested data must still be counted normally"
        assert body["at_risk_count"] is None, \
            "no predictions in scope must report None ('not yet scored'), not 0 ('nobody at risk')"
    finally:
        main_mod._DATA = original_data
        await _cleanup()


@pytest.mark.asyncio
async def test_at_risk_count_dedupes_a_student_flagged_in_multiple_subjects():
    """The same student is predicted Safe in one subject but At Risk in
    another, in the same period — must count that student exactly once in
    the institution-wide total, not twice, mirroring how total_students
    itself already counts distinct students across all their subjects."""
    original_data = main_mod._DATA
    df = pd.concat([
        _synthetic_df(),
        pd.DataFrame([{
            "STUDENTID_MASKED": "AtRiskStudentSafe", "SUBJECTCODE": TEST_SUBJECT2, "STUDYPERIOD": TEST_PERIOD,
            "MARKPERCENT": 90.0, "WEIGHTING": 100.0,
            "ASSESSMENTTYPECODE": "Exam", "STUDYPACKAGEASSESSMENTID": 99,
        }]),
    ], ignore_index=True)
    main_mod._DATA = df
    try:
        await _cleanup()
        await _seed_prediction(student="AtRiskStudentSafe",   subject=TEST_SUBJECT,  risk_band="At Risk")
        await _seed_prediction(student="AtRiskStudentSafe",   subject=TEST_SUBJECT2, risk_band="Safe")
        await _seed_prediction(student="AtRiskStudentAtRisk", subject=TEST_SUBJECT,  risk_band="At Risk")
        await _seed_prediction(student="AtRiskStudentHigh",   subject=TEST_SUBJECT,  risk_band="Safe")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client)
            res = await client.get(
                "/api/dashboard/summary", headers={"Authorization": f"Bearer {token}"},
                params={"trimester": TEST_PERIOD},
            )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["total_students"] == 3
        assert body["at_risk_count"] == 2, \
            "AtRiskStudentSafe (at-risk in one subject, safe in another) must count once, not twice"
    finally:
        main_mod._DATA = original_data
        await _cleanup()

"""
EDAPT v2 — GET /api/students-at-risk.

Verifies the cross-subject aggregation actually combines multiple subjects
into one list (not just re-exposing a single subject's roster), and that
role-based visibility matches subject_roster()'s own rule: a lecturer only
ever sees rows for subjects they're assigned to.

Uses real, SAFE_SUBJECTS-eligible subject codes (not the fake TEST100/
TEST101 used elsewhere in test_ingestion_e2e.py) because subject_roster()
declines to score any subject absent from subject_reliability.json — a
synthetic subject would make every row disappear (prediction_available:
False), which would test nothing about the aggregation logic itself. Same
technique test_ingestion_e2e.py's retrain test already uses for the same
reason.
"""

import io

import pandas as pd
import pytest
from httpx import AsyncClient, ASGITransport

import app.main as main_mod
from app.main import app
from app.ml import train_model
from tests.test_ingestion_e2e import (
    _login,
    _analyze_and_get_job,
    _confirm_and_get_job,
    _preserve_app_state,
    _isolate_ml_paths,
)


@pytest.mark.asyncio
async def test_students_at_risk_aggregates_across_subjects_and_scopes_lecturer_by_subject():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await _login(client)
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        real_df = pd.read_csv(train_model.DATA_PATH)
        real_df.columns = [c.strip() for c in real_df.columns]
        periods = real_df["STUDYPERIOD"].apply(lambda x: str(round(float(x), 1)))
        latest = sorted(periods.unique(), key=float)[-1]
        latest_df = real_df[periods == latest]

        reliable = (
            set(main_mod._SUBJECT_RELIABILITY.get("fully_clean", []))
            | set(main_mod._SUBJECT_RELIABILITY.get("mostly_clean", []))
        )
        lecturer_subjects = {"ICT104", "ICT201", "ICT301"}  # see _seed_default_users

        in_subject = next(
            s for s in latest_df["SUBJECTCODE"].unique()
            if s in reliable and s in lecturer_subjects
        )
        outside_subject = next(
            s for s in latest_df["SUBJECTCODE"].unique()
            if s in reliable and s not in lecturer_subjects
        )

        subset = latest_df[latest_df["SUBJECTCODE"].isin([in_subject, outside_subject])].copy()
        buf = io.StringIO()
        subset.to_csv(buf, index=False)
        csv_bytes = buf.getvalue().encode()

        async with _preserve_app_state():
            analyze_job = await _analyze_and_get_job(client, admin_headers, "capstone", "two_subjects.csv", csv_bytes)
            assert analyze_job["status"] == "success", analyze_job.get("error_detail")
            with _isolate_ml_paths(seed_live_period=latest):
                job = await _confirm_and_get_job(client, admin_headers, "capstone", analyze_job["result"]["token"])
            assert job["status"] == "success", job.get("error_detail")

            # ── Admin sees both subjects, combined into one list ──
            r = await client.get(
                "/api/students-at-risk", headers=admin_headers, params={"study_period": latest},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["subjects_included"] == 2
            assert {row["subject"] for row in body["students"]} == {in_subject, outside_subject}
            assert body["total_rows"] == len(body["students"]) > 0
            for row in body["students"]:
                assert "risk_band" in row and "student_id" in row and "subject" in row

            # ── Lecturer only sees the subject they're assigned to ──
            lect_login = await client.post(
                "/api/auth/login", json={"email": "user", "password": "Lect@2025!"},
            )
            lect_headers = {"Authorization": f"Bearer {lect_login.json()['access_token']}"}
            r2 = await client.get(
                "/api/students-at-risk", headers=lect_headers, params={"study_period": latest},
            )
            assert r2.status_code == 200
            body2 = r2.json()
            assert body2["subjects_included"] == 1
            assert {row["subject"] for row in body2["students"]} == {in_subject}


@pytest.mark.asyncio
async def test_students_at_risk_requires_data():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}
        async with _preserve_app_state():
            main_mod._DATA = None
            r = await client.get(
                "/api/students-at-risk", headers=headers, params={"study_period": "1.1"},
            )
        assert r.status_code == 503

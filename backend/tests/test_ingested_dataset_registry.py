"""
EDAPT v2 — Ingested dataset registry: GET /api/ingest/dataset-summary's
filename/mode/uploaded_by/uploaded_at fields, and DELETE
/api/ingest/datasets/{kind} clearing the live dataset.

Covers a real bug caught during manual testing of this feature: right
after a DELETE, dataset-summary kept reporting the just-cleared job's
filename/mode next to has_data: false, because "the last successful job"
and "the job whose data is still actually live" aren't the same query
once a clear has happened — fixed via IngestJob.cleared_at (see that
column's docstring in app/db/models.py).
"""

import io

import pandas as pd
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from tests.test_ingestion_e2e import (
    _login,
    _analyze_and_get_job,
    _confirm_and_get_job,
    _preserve_app_state,
    _isolate_ml_paths,
)


def _build_capstone_csv(subject="TEST100", period=99.1, student="RegistryTestStudent1"):
    rows = [{
        "ASSESSMENTTYPECODE": "EXAM", "ATTEMPTNUMBER": 1, "ASSESSMENTMARK": 70,
        "MAXMARK": 100, "WEIGHTING": 100, "GENDERCODE": "M", "AGEGROUP": "20-24",
        "STUDYPERIOD": period, "SUBJECTCODE": subject, "CLASSGROUP": "C1",
        "MARKPERCENT": 70, "STUDENTID_MASKED": student, "COUNTRY_MASKED": "AU",
    }]
    buf = io.StringIO()
    pd.DataFrame(rows).to_csv(buf, index=False)
    return buf.getvalue().encode()


@pytest.mark.asyncio
async def test_dataset_summary_reports_filename_mode_and_uploader_after_confirm():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        async with _preserve_app_state():
            csv_bytes = _build_capstone_csv()
            analyze_job = await _analyze_and_get_job(client, headers, "capstone", "registry_test.csv", csv_bytes)
            assert analyze_job["status"] == "success", analyze_job.get("error_detail")
            with _isolate_ml_paths():
                job = await _confirm_and_get_job(client, headers, "capstone", analyze_job["result"]["token"])
            assert job["status"] == "success", job.get("error_detail")

            summary = (await client.get("/api/ingest/dataset-summary", headers=headers)).json()
            cap = summary["capstone"]
            assert cap["has_data"] is True
            assert cap["filename"] == "registry_test.csv"
            assert cap["mode"] == "override"
            assert cap["uploaded_by"] == "admin"
            assert cap["uploaded_at"]


@pytest.mark.asyncio
async def test_delete_dataset_clears_data_and_stops_reporting_stale_metadata():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        async with _preserve_app_state():
            csv_bytes = _build_capstone_csv()
            analyze_job = await _analyze_and_get_job(client, headers, "capstone", "registry_test.csv", csv_bytes)
            with _isolate_ml_paths():
                job = await _confirm_and_get_job(client, headers, "capstone", analyze_job["result"]["token"])
            assert job["status"] == "success", job.get("error_detail")

            before = (await client.get("/api/ingest/dataset-summary", headers=headers)).json()
            assert before["capstone"]["has_data"] is True

            del_res = await client.delete("/api/ingest/datasets/capstone", headers=headers)
            assert del_res.status_code == 200
            assert del_res.json() == {"kind": "capstone", "cleared": True, "has_data": False}

            after = (await client.get("/api/ingest/dataset-summary", headers=headers)).json()
            cap = after["capstone"]
            assert cap["has_data"] is False
            # The real bug this regression-tests: these used to keep
            # showing the cleared job's info even with has_data: false.
            assert cap["filename"] is None
            assert cap["mode"] is None
            assert cap["uploaded_by"] is None
            assert cap["uploaded_at"] is None


@pytest.mark.asyncio
async def test_delete_dataset_rejects_lecturer():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        login = await client.post("/api/auth/login", json={"email": "user", "password": "Lect@2025!"})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        res = await client.delete("/api/ingest/datasets/capstone", headers=headers)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_delete_dataset_rejects_unknown_kind():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}
        res = await client.delete("/api/ingest/datasets/nonsense", headers=headers)
    assert res.status_code == 404

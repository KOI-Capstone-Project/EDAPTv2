"""
EDAPT v2 — controlling a bulk risk-scoring run: cancelling one that's stuck
or unwanted, and self-healing one left orphaned by a process that died.

Real gap this closes: a ScoringJob has no way to stop early once started,
and POST /api/scoring/run refuses (409) while any row says "running" — so a
job orphaned by a killed backend process (confirmed as a real incident:
rows left "running" for days after this dev container was force-killed
mid-job) permanently blocks every future scoring run until someone finds
and manually fixes the stuck row. Two fixes, tested here:
  - POST /api/scoring/jobs/{id}/cancel actually stops a running job (via
    asyncio.Task.cancel(), not just flipping a database flag) and clears
    the 409 guard immediately.
  - The app's own startup handler marks any row still "running" as failed
    the moment a fresh process starts — such a row cannot be a real,
    still-executing job, since whatever asyncio task was running it died
    with whatever process created it.
"""
import asyncio

import pandas as pd
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete

import app.main as main_mod
from app.db.models import ScoringJob
from app.main import app

TEST_PERIOD = "88.8"  # synthetic — never a real ingested period
N_SUBJECTS = 5


def _synthetic_df():
    return pd.DataFrame([
        {
            "STUDENTID_MASKED": f"CancelStudent{i}", "SUBJECTCODE": f"CANCEL10{i}",
            "STUDYPERIOD": TEST_PERIOD, "MARKPERCENT": 80.0, "WEIGHTING": 100.0,
            "ASSESSMENTTYPECODE": "Exam", "STUDYPACKAGEASSESSMENTID": i,
        }
        for i in range(N_SUBJECTS)
    ])


async def _login(client) -> str:
    res = await client.post("/api/auth/login", json={"email": "admin", "password": "Admin@2025!"})
    return res.json()["access_token"]


async def _clear_scoring_jobs(*job_ids: int):
    """Deletes only the specific rows THIS test created — never a blanket
    `delete(ScoringJob)`. A real, live scoring job (from a real ingestion,
    unrelated to this test entirely) sits in the exact same shared table;
    wiping the whole thing was confirmed live to delete a real in-progress
    job's row out from under it the moment this suite happened to run."""
    if not job_ids:
        return
    async with main_mod._AsyncSession() as db:
        await db.execute(delete(ScoringJob).where(ScoringJob.id.in_(job_ids)))
        await db.commit()


@pytest.mark.asyncio
async def test_cancel_stops_a_running_scoring_job_and_clears_the_409_guard(monkeypatch):
    original_data = main_mod._DATA
    original_reliability = main_mod._SUBJECT_RELIABILITY
    main_mod._DATA = _synthetic_df()
    main_mod._SUBJECT_RELIABILITY = {
        "fully_clean": [f"CANCEL10{i}" for i in range(N_SUBJECTS)], "mostly_clean": [],
    }

    # Slow enough to reliably cancel mid-run, fast enough to keep the test quick.
    async def slow_compute_roster_rows(*args, **kwargs):
        await asyncio.sleep(1.5)
        return [{"student_id": "x", "probability": 50.0}]

    monkeypatch.setattr(main_mod, "_compute_roster_rows", slow_compute_roster_rows)
    created_job_ids: list[int] = []

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client)
            headers = {"Authorization": f"Bearer {token}"}

            run_res = await client.post(
                "/api/scoring/run", headers=headers, json={"study_periods": [TEST_PERIOD]},
            )
            assert run_res.status_code == 202, run_res.text
            job_id = run_res.json()["job_id"]
            created_job_ids.append(job_id)

            # A second run must be refused while this one is genuinely in progress.
            blocked = await client.post(
                "/api/scoring/run", headers=headers, json={"study_periods": [TEST_PERIOD]},
            )
            assert blocked.status_code == 409

            await asyncio.sleep(0.3)  # let it actually start scoring
            cancel_res = await client.post(f"/api/scoring/jobs/{job_id}/cancel", headers=headers)
            assert cancel_res.status_code == 200, cancel_res.text
            body = cancel_res.json()
            assert body["status"] == "failed"
            assert "Cancelled by" in body["error_detail"]

            completed_at_cancel = body["subjects_completed"]
            # Long enough that an *uncancelled* job (with N_SUBJECTS/concurrency
            # slow calls left) would clearly have kept advancing by now.
            await asyncio.sleep(2.5)

            check = await client.get(f"/api/scoring/jobs/{job_id}", headers=headers)
            check_body = check.json()
            assert check_body["subjects_completed"] == completed_at_cancel, \
                "a cancelled job must not keep making progress"
            assert check_body["status"] == "failed"

            # And the 409 guard must be clear immediately — the real point
            # of cancel: unblocking a fresh scan of newly-ingested data.
            new_run = await client.post(
                "/api/scoring/run", headers=headers, json={"study_periods": [TEST_PERIOD]},
            )
            assert new_run.status_code == 202, new_run.text
            new_job_id = new_run.json()["job_id"]
            created_job_ids.append(new_job_id)
            await client.post(f"/api/scoring/jobs/{new_job_id}/cancel", headers=headers)
    finally:
        main_mod._DATA = original_data
        main_mod._SUBJECT_RELIABILITY = original_reliability
        await _clear_scoring_jobs(*created_job_ids)


@pytest.mark.asyncio
async def test_two_auto_triggered_jobs_run_one_at_a_time_not_concurrently(monkeypatch):
    """Real, reported behavior: a capstone ingestion and an attendance
    ingestion each auto-trigger their own ScoringJob independently, with no
    check for one already running — a completely normal workflow (upload
    marks, then upload attendance) used to launch both concurrently,
    doubling CPU contention for no benefit. _SCORING_SERIAL_LOCK means the
    second job sits at 0 subjects_completed, genuinely not yet doing any
    per-subject work, until the first one finishes."""
    original_data = main_mod._DATA
    original_reliability = main_mod._SUBJECT_RELIABILITY
    main_mod._DATA = _synthetic_df()
    main_mod._SUBJECT_RELIABILITY = {
        "fully_clean": [f"CANCEL10{i}" for i in range(N_SUBJECTS)], "mostly_clean": [],
    }

    async def slow_compute_roster_rows(*args, **kwargs):
        await asyncio.sleep(1.0)
        return [{"student_id": "x", "probability": 50.0}]

    monkeypatch.setattr(main_mod, "_compute_roster_rows", slow_compute_roster_rows)

    async def _make_job() -> int:
        async with main_mod._AsyncSession() as db:
            job = ScoringJob(
                status="running", trigger="auto_after_ingest", study_periods=[TEST_PERIOD],
                subjects_total=0, subjects_completed=0, students_scored=0,
                started_by="system",
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)
            return job.id

    job_a = job_b = None
    try:
        job_a = await _make_job()
        main_mod._launch_scoring_job(job_a, [TEST_PERIOD])
        await asyncio.sleep(0.2)  # let job A actually start scoring

        job_b = await _make_job()
        main_mod._launch_scoring_job(job_b, [TEST_PERIOD])
        await asyncio.sleep(1.3)  # long enough for job A to make real progress

        async with main_mod._AsyncSession() as db:
            refreshed_a = await db.get(ScoringJob, job_a)
            refreshed_b = await db.get(ScoringJob, job_b)

        assert refreshed_a.subjects_completed > 0, "job A should be actively progressing"
        assert refreshed_b.subjects_completed == 0, \
            "job B must not do any per-subject work while job A still holds the serial lock"
        assert refreshed_b.status == "running", "job B is running (queued), not failed or stuck elsewhere"

        for jid in (job_a, job_b):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                token = await _login(client)
                await client.post(f"/api/scoring/jobs/{jid}/cancel", headers={"Authorization": f"Bearer {token}"})
    finally:
        main_mod._DATA = original_data
        main_mod._SUBJECT_RELIABILITY = original_reliability
        await _clear_scoring_jobs(*(jid for jid in (job_a, job_b) if jid is not None))


@pytest.mark.asyncio
async def test_cancel_rejects_a_job_that_is_not_running():
    async with main_mod._AsyncSession() as db:
        job = ScoringJob(
            status="success", trigger="manual", study_periods=[TEST_PERIOD],
            subjects_total=1, subjects_completed=1, students_scored=1,
            started_by="test",
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id = job.id

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            token = await _login(client)
            res = await client.post(
                f"/api/scoring/jobs/{job_id}/cancel", headers={"Authorization": f"Bearer {token}"},
            )
        assert res.status_code == 400
    finally:
        await _clear_scoring_jobs(job_id)


@pytest.mark.asyncio
async def test_startup_marks_an_orphaned_running_job_as_failed():
    """A row still 'running' when a fresh process starts cannot be a real,
    live job — whatever asyncio task was running it died with whatever
    process created it. Confirmed live: three such rows, days old, were
    found blocking every scoring run after this dev container had been
    killed mid-job."""
    async with main_mod._AsyncSession() as db:
        job = ScoringJob(
            status="running", trigger="manual", study_periods=["77.7"],
            subjects_total=5, subjects_completed=1, students_scored=10,
            started_by="orphan-test",
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id = job.id

    try:
        await app.router.startup()  # same call conftest.py's own fixture uses

        async with main_mod._AsyncSession() as db:
            refreshed = await db.get(ScoringJob, job_id)
            assert refreshed.status == "failed"
            assert "Orphaned" in refreshed.error_detail
            assert refreshed.finished_at is not None
    finally:
        await _clear_scoring_jobs(job_id)

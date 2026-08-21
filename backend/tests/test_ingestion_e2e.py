"""
EDAPT v2 — End-to-end tests for the two-phase ingestion pipeline
(analyze -> confirm, for both capstone and attendance CSVs), covering the
full chain: column classification, the collapse_attempts_to_latest_per_type
resit fix, attendance feature computation, live dashboard reflection, and
the new-period retrain trigger (registration only, never auto-promotion).

Separate file from test_smoke.py, per the build spec. Every test that
mutates app.main's in-memory _DATA/_ATTENDANCE/_PENDING_INGESTS restores
the originals afterward (see _preserve_app_state), and every test that
touches the ML registry/DATA_PATH constants is fully isolated to a
throwaway temp directory (see _isolate_ml_paths) — the same pattern
already used by app/ml/verify_dynamic_period_e2e.py — so nothing here
ever writes to the real data/Capstone_data_20260729.csv or the real
backend/app/ml/models/registry.json.
"""

import contextlib
import io
import json
import multiprocessing
import shutil
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete, select

import app.main as main_mod
from app.main import app
from app.ml import train_model, check_new_period, model_registry

CAPSTONE_COLUMNS = [
    "ASSESSMENTTYPECODE", "ATTEMPTNUMBER", "ASSESSMENTMARK", "MAXMARK",
    "WEIGHTING", "GENDERCODE", "AGEGROUP", "STUDYPERIOD", "SUBJECTCODE",
    "CLASSGROUP", "MARKPERCENT", "STUDENTID_MASKED", "COUNTRY_MASKED",
]


async def _login(client) -> str:
    login = await client.post("/api/auth/login", json={"email": "admin", "password": "Admin@2025!"})
    return login.json()["access_token"]


async def _confirm_and_get_job(client, headers, kind: str, token: str) -> dict:
    """
    Confirm now returns 202 + a job id immediately (the actual parse/
    retrain-check/commit work runs via FastAPI BackgroundTasks, not inline
    in the request) instead of the old synchronous 200-with-full-result.
    Fetches the finished job's status/result via GET /api/ingest/jobs/{id}
    so tests can assert on the same fields as before.

    No polling loop needed: httpx's ASGITransport calls the app in-process
    with no real server boundary, and Starlette runs BackgroundTasks via a
    plain `await` inside Response.__call__ before the ASGI call returns —
    so by the time `client.post(...)` comes back here, the background job
    has already run to completion.
    """
    res = await client.post(f"/api/ingest/{kind}/confirm", headers=headers, json={"token": token})
    assert res.status_code == 202, f"expected 202-accepted, got {res.status_code}: {res.text}"
    job_id = res.json()["job_id"]
    job_res = await client.get(f"/api/ingest/jobs/{job_id}", headers=headers)
    assert job_res.status_code == 200
    job = job_res.json()
    assert job["status"] != "running", "background job did not finish synchronously as expected under ASGITransport"
    return job


async def _analyze_and_get_job(client, headers, kind: str, filename: str, csv_bytes: bytes) -> dict:
    """
    Analyze now returns 202 + a job id immediately (the actual parse/
    classify work runs via FastAPI BackgroundTasks, same reasoning as
    _confirm_and_get_job above — a page refresh mid-analysis must not lose
    the upload). Fetches the finished job via GET /api/ingest/analyze-jobs/{id}
    so tests can assert on job["result"], the same shape the old
    synchronous 200 response used to return directly.
    """
    res = await client.post(
        f"/api/ingest/{kind}/analyze", headers=headers,
        files={"file": (filename, csv_bytes, "text/csv")},
    )
    assert res.status_code == 202, f"expected 202-accepted, got {res.status_code}: {res.text}"
    job_id = res.json()["job_id"]
    job_res = await client.get(f"/api/ingest/analyze-jobs/{job_id}", headers=headers)
    assert job_res.status_code == 200
    job = job_res.json()
    assert job["status"] != "running", "background analyze job did not finish synchronously as expected under ASGITransport"
    return job


def _lock_contention_worker(role: str, hold_seconds: float, result_path: str) -> None:
    """
    Runs in a genuinely separate OS process (see the test below) — the
    actual scenario _acquire_ingest_lock exists to protect against is
    prod's 4 separate gunicorn worker processes, not same-process asyncio
    interleaving (which Python's single-threaded event loop, combined
    with this lock's blocking time.sleep() polling, would trivially
    serialize anyway and wouldn't prove anything about the real risk).

    role "A" acquires first (by design — see the 0.5s stagger the caller
    gives "B") and holds the lock for hold_seconds, simulating a real
    ingest's disk-write + retrain work. role "B" attempts shortly after
    and must block until A releases. Real wall-clock timestamps for each
    phase are written to result_path so the test can verify actual
    ordering, not just "no exception was raised".
    """
    import app.main as m

    if role == "B":
        time.sleep(0.5)  # let A reach the lock first, deterministically

    attempt_start = time.time()
    m._acquire_ingest_lock()
    acquired = time.time()

    if role == "A":
        time.sleep(hold_seconds)  # simulate real ingest/retrain work while holding the lock

    before_release = time.time()
    m._release_ingest_lock()
    released = time.time()

    with open(result_path, "w") as f:
        json.dump({
            "role": role, "attempt_start": attempt_start, "acquired": acquired,
            "before_release": before_release, "released": released,
        }, f)


def _row(student, subject, period, atype, attempt, mark, weighting, maxmark=None,
         gender="M", age="21~30", country="Country0", classgroup="CG1"):
    maxmark = weighting if maxmark is None else maxmark
    return {
        "ASSESSMENTTYPECODE": atype, "ATTEMPTNUMBER": attempt,
        "ASSESSMENTMARK": mark * maxmark / 100, "MAXMARK": maxmark, "WEIGHTING": weighting,
        "GENDERCODE": gender, "AGEGROUP": age, "STUDYPERIOD": period, "SUBJECTCODE": subject,
        "CLASSGROUP": classgroup, "MARKPERCENT": mark, "STUDENTID_MASKED": student,
        "COUNTRY_MASKED": country,
    }


def _build_nine_case_csv(include_unexpected_column: bool = True) -> bytes:
    """
    9 real, distinct scenarios (per the build spec):
      1. clean pass          — StudentP1/TEST100, 100% weighting, high marks -> PASS
      2. clean fail          — StudentF1/TEST100, 100% weighting, low marks -> FAIL
      3. incomplete/anomalous— StudentI1/TEST100, only 60% weighting recorded
      4. resit                — StudentR1/TEST100, attempt-1 partial (TX only) + attempt-2
                                 completes it (FE) — tests collapse_attempts_to_latest_per_type
                                 combines across attempts at the assessment-type level
      5. weighting anomaly    — StudentW1/TEST100, 110% weighting (over)
      6. control clean case   — StudentC1/TEST101, independent clean pass, different subject
      7. MAXMARK != WEIGHTING — StudentM1/TEST100, MAXMARK=20 but WEIGHTING=15
      8. curriculum-change    — StudentU1/TEST100, a later period with an entirely different
                                 assessment-type set (PROJ instead of TX/FE)
      9. null demographics    — StudentN1/TEST100, GENDERCODE/AGEGROUP/COUNTRY_MASKED blank
    Plus one deliberately unexpected column ("NOTES") to verify it's classified NEW, not
    silently dropped or silently kept.
    """
    rows = [
        _row("StudentP1", "TEST100", "99.1", "TX", 1, 80, 50),
        _row("StudentP1", "TEST100", "99.1", "FE", 1, 80, 50),

        _row("StudentF1", "TEST100", "99.1", "TX", 1, 20, 50),
        _row("StudentF1", "TEST100", "99.1", "FE", 1, 20, 50),

        _row("StudentI1", "TEST100", "99.1", "TX", 1, 70, 60),

        _row("StudentR1", "TEST100", "99.1", "TX", 1, 40, 50),
        _row("StudentR1", "TEST100", "99.1", "FE", 2, 90, 50),

        _row("StudentW1", "TEST100", "99.1", "TX", 1, 60, 60),
        _row("StudentW1", "TEST100", "99.1", "FE", 1, 60, 50),

        _row("StudentC1", "TEST101", "99.1", "TX", 1, 75, 50),
        _row("StudentC1", "TEST101", "99.1", "FE", 1, 75, 50),

        _row("StudentM1", "TEST100", "99.1", "TX", 1, 65, 50, maxmark=20),

        _row("StudentU1", "TEST100", "99.2", "PROJ", 1, 85, 100),

        _row("StudentN1", "TEST100", "99.1", "TX", 1, 55, 50,
             gender="", age="", country=""),
        _row("StudentN1", "TEST100", "99.1", "FE", 1, 55, 50,
             gender="", age="", country=""),
    ]
    df = pd.DataFrame(rows)
    if include_unexpected_column:
        df["NOTES"] = "placeholder"
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


def _build_known_attendance_csv() -> bytes:
    """
    A real-subject attendance CSV (ICT104/T3/2025, so it passes
    build_attendance_features()'s "course in current capstone subjects"
    filter against the real, unpatched capstone file) with a KNOWN
    7-present-of-10-sessions case for a synthetic test student —
    verifies ATTENDANCE_RATE computes to exactly 0.70.
    """
    codes = ["H"] * 7 + ["N"] * 2 + ["A"] * 1  # 7 present, 2 unexplained, 1 authorized = 10 total
    rows = [
        {
            "STUDENTID_MASKED": "StudentAttnTest1", "course": "ICT104",
            "location_code": "L1", "building": "B1", "room": "R1",
            "study_period_code": "T3", "year": "2025",
            "class_no": "1", "actv_no": "1", "cls_session_no": i + 1,
            "attendance_code": code,
        }
        for i, code in enumerate(codes)
    ]
    buf = io.StringIO()
    pd.DataFrame(rows).to_csv(buf, index=False)
    return buf.getvalue().encode()


@contextlib.contextmanager
def _isolate_ml_paths(seed_live_period: str | None = None):
    """
    Full isolation for DATA_PATH / check_new_period.DATA_PATH / the model
    registry — same pattern as verify_dynamic_period_e2e.py. Nothing here
    touches the real data/Capstone_data_20260729.csv or the real
    backend/app/ml/models/registry.json. If seed_live_period is given, the
    isolated registry starts with a minimal fake "live" entry at that
    validated_on period (no real .pkl needed — get_live_entry() is a plain
    dict lookup), so new-period comparison logic has something real to
    compare against.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="edapt_ingestion_e2e_"))
    isolated_models_dir = tmp_dir / "models"
    isolated_models_dir.mkdir(parents=True, exist_ok=True)
    isolated_registry_path = isolated_models_dir / "registry.json"

    if seed_live_period is not None:
        seed_registry = {
            "live_version": "seed_v1",
            "versions": [{
                "version": "seed_v1", "file": "seed_v1.pkl",
                "trained_at": "2026-01-01T00:00:00+00:00",
                "accuracy": 0.9, "decision_threshold": 0.5,
                "validated_on": seed_live_period,
                "classification_report": {},
            }],
            "promotion_history": [],
        }
        with open(isolated_registry_path, "w") as f:
            json.dump(seed_registry, f)

    original = {
        "train_model.DATA_PATH":          train_model.DATA_PATH,
        "check_new_period.DATA_PATH":     check_new_period.DATA_PATH,
        "model_registry.MODELS_DIR":      model_registry.MODELS_DIR,
        "model_registry.REGISTRY_PATH":   model_registry.REGISTRY_PATH,
        "model_registry.LEGACY_PKL_PATH": model_registry.LEGACY_PKL_PATH,
    }
    try:
        model_registry.MODELS_DIR      = isolated_models_dir
        model_registry.REGISTRY_PATH   = isolated_registry_path
        model_registry.LEGACY_PKL_PATH = tmp_dir / "no_legacy_here.pkl"
        yield tmp_dir, isolated_registry_path
    finally:
        train_model.DATA_PATH          = original["train_model.DATA_PATH"]
        check_new_period.DATA_PATH     = original["check_new_period.DATA_PATH"]
        model_registry.MODELS_DIR      = original["model_registry.MODELS_DIR"]
        model_registry.REGISTRY_PATH   = original["model_registry.REGISTRY_PATH"]
        model_registry.LEGACY_PKL_PATH = original["model_registry.LEGACY_PKL_PATH"]
        shutil.rmtree(tmp_dir, ignore_errors=True)


@contextlib.asynccontextmanager
async def _preserve_app_state():
    """
    Snapshot + restore app.main's live in-memory dataset globals around a
    test, clean up any pending_ingests / ingest_jobs / analyze_jobs DB rows
    the test created (all SHARED, cross-worker Postgres tables — see
    PendingIngest, IngestJob and AnalyzeJob in app/db/models.py — so leftover test rows
    would show up in the real dev server's own pending-upload flow and
    ingestion notification badge too, not just this process), and delete
    backend/app/ml/ingested_capstone.csv if a test left synthetic data
    there. That file is now train_model.DATA_PATH's
    real, persistent override target (see train_model.py) — read fresh by
    ANY independent process, including the real scheduler and a real
    admin's manual check_new_period.py run — so leaving fake test rows
    (STUDYPERIOD 99.1/99.2, subjects TEST100/TEST101) there after a test
    run would silently corrupt what the real dev environment resolves as
    "the current data" until someone noticed or re-ingested real data.
    """
    original_data       = main_mod._DATA
    original_attendance = main_mod._ATTENDANCE
    ingested_override_path = Path(main_mod.__file__).parent / "ml" / "ingested_capstone.csv"
    original_override_bytes = ingested_override_path.read_bytes() if ingested_override_path.exists() else None
    try:
        yield
    finally:
        main_mod._DATA       = original_data
        main_mod._ATTENDANCE = original_attendance
        async with main_mod._AsyncSession() as session:
            from app.db.models import AnalyzeJob, IngestJob, PendingIngest
            await session.execute(delete(PendingIngest))
            await session.execute(delete(IngestJob))
            await session.execute(delete(AnalyzeJob))
            await session.commit()
        # Restore, not just delete — a real admin's previously-ingested
        # real data (if this file existed before the test touched it) must
        # not be silently lost.
        if original_override_bytes is None:
            ingested_override_path.unlink(missing_ok=True)
        else:
            ingested_override_path.write_bytes(original_override_bytes)


# ── Test -1 — .ingest.lock under REAL concurrent contention (two OS processes) ──

def test_ingest_lock_serializes_two_real_concurrent_processes():
    """
    Fires two genuinely separate OS processes (multiprocessing.Process,
    not asyncio.gather within one process/one event loop — a same-process
    test wouldn't prove anything about the real risk, since Python's GIL
    plus this lock's blocking time.sleep() would trivially serialize
    same-process coroutines regardless of whether the lock worked at
    all). Both race for the same _INGEST_LOCK_PATH. Expected: A acquires
    first and holds it for 3s (simulating real ingest/retrain work); B's
    attempt blocks until A releases, then B acquires cleanly — no
    exception, no hang past the join timeout, and B's real acquired
    timestamp is provably after A's real released timestamp.
    """
    import app.main as m

    m._INGEST_LOCK_PATH.unlink(missing_ok=True)  # start from a clean, unlocked state

    with tempfile.TemporaryDirectory() as tmp_dir:
        result_a = Path(tmp_dir) / "result_a.json"
        result_b = Path(tmp_dir) / "result_b.json"

        p_a = multiprocessing.Process(target=_lock_contention_worker, args=("A", 3.0, str(result_a)))
        p_b = multiprocessing.Process(target=_lock_contention_worker, args=("B", 0.0, str(result_b)))

        wall_start = time.time()
        p_a.start()
        p_b.start()
        p_a.join(timeout=30)
        p_b.join(timeout=30)
        wall_elapsed = time.time() - wall_start

        assert not p_a.is_alive(), "process A did not finish within 30s — likely hung, not a clean lock failure"
        assert not p_b.is_alive(), "process B did not finish within 30s — likely hung, not a clean lock failure"
        assert p_a.exitcode == 0, f"process A crashed (exitcode {p_a.exitcode})"
        assert p_b.exitcode == 0, f"process B crashed (exitcode {p_b.exitcode})"
        assert result_a.exists() and result_b.exists(), (
            "one process never reached the point of writing its result — check for a silent crash"
        )

        with open(result_a) as f:
            ra = json.load(f)
        with open(result_b) as f:
            rb = json.load(f)

        print(
            f"\n[lock contention] wall_elapsed={wall_elapsed:.2f}s\n"
            f"  A: attempt={ra['attempt_start']:.3f}  acquired={ra['acquired']:.3f}  released={ra['released']:.3f}\n"
            f"  B: attempt={rb['attempt_start']:.3f}  acquired={rb['acquired']:.3f}  released={rb['released']:.3f}"
        )

        # The real proof: B's ACTUAL acquisition happened only after A's
        # ACTUAL release — not "the test passed", real timestamps in the
        # real order the lock is supposed to enforce.
        assert rb["acquired"] >= ra["released"], (
            f"RACE CONDITION: B acquired the lock at {rb['acquired']:.3f}, "
            f"BEFORE A released it at {ra['released']:.3f} — the lock did not serialize them."
        )
        # And the whole exchange took roughly A's hold time, not
        # instantaneous (which would mean the "wait" was fake) and not
        # dramatically longer (which would mean excessive polling backoff).
        assert 2.5 <= wall_elapsed <= 8.0, f"unexpected total wall time {wall_elapsed:.2f}s for a 3s hold + 0.5s stagger"


# ── Test 0 — cross-worker pending-ingest handoff (Priority 1 fix) ──────────────
#
# A single-process test where "analyze" and "confirm" run in the SAME
# AsyncClient would not actually prove the multi-worker fix — it would
# pass even with the OLD in-memory dict, since both calls share the same
# Python process either way. This test proves the real thing: it writes
# the pending row directly via a fresh, independent DB session (never
# calling the analyze endpoint at all), so there is zero shared in-process
# state between "the analyze side" and "the confirm side" — the only
# thing bridging them is the pending_ingests table. If confirm still
# succeeds and produces the correct data, that's real proof it depends
# only on the shared DB store, which is exactly what makes it safe across
# gunicorn's 4 separate worker processes in prod.

@pytest.mark.asyncio
async def test_confirm_works_from_a_pending_row_it_never_wrote_itself():
    from app.db.models import PendingIngest

    csv_bytes = _build_nine_case_csv(include_unexpected_column=False)
    token = "cross-worker-test-token-0001"

    async with _preserve_app_state():
        # Simulate "worker A": write the pending row directly to Postgres,
        # completely bypassing /api/ingest/capstone/analyze and therefore
        # any in-process object analyze() might have touched.
        async with main_mod._AsyncSession() as session:
            session.add(PendingIngest(
                kind="capstone", token=token, filename="cross_worker_test.csv",
                csv_bytes=csv_bytes,
            ))
            await session.commit()

        # Simulate "worker B": a fresh client hitting confirm with a token
        # it never generated and a pending row it never created in memory.
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            auth_token = await _login(client)
            headers = {"Authorization": f"Bearer {auth_token}"}
            with _isolate_ml_paths(seed_live_period="99.9"):  # newer than the data -> no retrain
                job = await _confirm_and_get_job(client, headers, "capstone", token)

    assert job["status"] == "success"
    result = job["result"]
    assert result["row_count"] == 15  # the 9-case CSV's real row count (9 scenarios, 15 rows total)
    assert result["retrain"]["triggered"] is False

    # And the row must be gone afterward — confirm() consumes it, so a
    # second confirm with the same token must now correctly 404.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        auth_token = await _login(client)
        headers = {"Authorization": f"Bearer {auth_token}"}
        replay = await client.post(
            "/api/ingest/capstone/confirm", headers=headers, json={"token": token},
        )
    assert replay.status_code == 404


# ── Test 0b — PENDING_INGEST_TTL_MINUTES actually rejects a stale row ──────────
#
# The 30-minute expiry has only ever existed as code, never been proven
# against a genuinely stale row. Inserts a pending row with created_at
# backdated well past the TTL, then confirms it's rejected — not silently
# committed against data a real admin might not even remember uploading.

@pytest.mark.asyncio
async def test_confirm_rejects_a_pending_row_older_than_the_ttl():
    from app.db.models import PendingIngest

    csv_bytes = _build_nine_case_csv(include_unexpected_column=False)
    token = "ttl-stress-test-token-0001"
    stale_timestamp = datetime.now(timezone.utc) - timedelta(minutes=main_mod.PENDING_INGEST_TTL_MINUTES + 5)

    async with _preserve_app_state():
        row_count_before = len(main_mod._DATA)
        async with main_mod._AsyncSession() as session:
            session.add(PendingIngest(
                kind="capstone", token=token, filename="ttl_stress_test.csv",
                csv_bytes=csv_bytes, created_at=stale_timestamp,
            ))
            await session.commit()

        # Confirm the row really did land with the backdated timestamp —
        # otherwise this test would trivially pass for the wrong reason.
        async with main_mod._AsyncSession() as session:
            result = await session.execute(select(PendingIngest).where(PendingIngest.kind == "capstone"))
            row = result.scalar_one()
            age_minutes = (datetime.now(timezone.utc) - row.created_at).total_seconds() / 60
            assert age_minutes > main_mod.PENDING_INGEST_TTL_MINUTES, (
                f"test setup failed: row age {age_minutes:.1f}min is not actually past the "
                f"{main_mod.PENDING_INGEST_TTL_MINUTES}min TTL — backdating didn't take effect"
            )

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            auth_token = await _login(client)
            headers = {"Authorization": f"Bearer {auth_token}"}
            res = await client.post(
                "/api/ingest/capstone/confirm", headers=headers, json={"token": token},
            )

    # Must fail cleanly — never silently commit a 40-minute-old upload.
    assert res.status_code == 404
    assert "expired" in res.json()["detail"].lower()

    # And the live data must be completely unchanged by the rejected attempt
    # — not just that the endpoint returned 404, but that nothing was
    # committed under the hood before the rejection.
    assert len(main_mod._DATA) == row_count_before


# ── Test 1 — column classification, including one deliberately unexpected column ──

@pytest.mark.asyncio
async def test_column_classification_flags_unexpected_column_as_new():
    csv_bytes = _build_nine_case_csv(include_unexpected_column=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}
        async with _preserve_app_state():
            job = await _analyze_and_get_job(client, headers, "capstone", "nine_case.csv", csv_bytes)
    assert job["status"] == "success", job.get("error_detail")
    cols = job["result"]["columns"]
    assert set(cols["keep"]) == set(CAPSTONE_COLUMNS)
    skip_names = {s["column"] for s in cols["skip"]}
    assert skip_names == set()  # none of the 4 known-skip columns are present in this synthetic file
    assert "NOTES" in cols["new"], "the deliberately unexpected column must be flagged NEW, not dropped or silently kept"


# ── Test 2 — row-level collapsing produces the expected result for the resit case ──

@pytest.mark.asyncio
async def test_resit_collapsing_combines_across_attempts_at_type_level():
    csv_bytes = _build_nine_case_csv(include_unexpected_column=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}
        async with _preserve_app_state():
            analyze_job = await _analyze_and_get_job(client, headers, "capstone", "nine_case.csv", csv_bytes)
            assert analyze_job["status"] == "success", analyze_job.get("error_detail")
            token_id = analyze_job["result"]["token"]
            with _isolate_ml_paths(seed_live_period="99.9"):  # newer than 99.2 -> no retrain triggered
                job = await _confirm_and_get_job(client, headers, "capstone", token_id)
            assert job["status"] == "success"
            assert job["result"]["retrain"]["triggered"] is False

            # StudentR1's resit: attempt-1 TX(50%,mark=40) + attempt-2 FE(50%,mark=90) should
            # COMBINE (not "latest attempt only", which would keep just FE and lose TX) —
            # weighted final = 40*0.5 + 90*0.5 = 65.0, which is a PASS (>=50).
            collapsed = train_model.collapse_attempts_to_latest_per_type(
                main_mod._DATA.dropna(subset=["MARKPERCENT"])
            )
            resit_rows = collapsed[collapsed["STUDENTID_MASKED"] == "StudentR1"]
            assert set(resit_rows["ASSESSMENTTYPECODE"]) == {"TX", "FE"}, \
                "naive latest-attempt-only collapsing would have dropped TX entirely"
            target = train_model.build_target(collapsed)
            resit_target = target[target["STUDENTID_MASKED"] == "StudentR1"].iloc[0]
            assert resit_target["PASS"] == 1  # 65.0 >= 50


# ── Test 3 — ATTENDANCE_RATE computes correctly on a known input (7/10 -> 0.70) ──

@pytest.mark.asyncio
async def test_attendance_rate_known_input():
    from app.ml.build_attendance_features import build_attendance_features

    att_bytes = _build_known_attendance_csv()
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(att_bytes)
        tmp_path = Path(tmp.name)
    try:
        features = build_attendance_features(attendance_path=tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    row = features[features["STUDENTID_MASKED"] == "StudentAttnTest1"].iloc[0]
    assert row["TOTAL_SESSIONS"] == 10
    assert row["SESSIONS_PRESENT"] == 7
    assert row["ATTENDANCE_RATE"] == pytest.approx(0.70)
    assert row["UNEXPLAINED_ABSENCE_RATE"] == pytest.approx(0.20)
    assert row["ABSENCE_RATE"] == pytest.approx(0.10)  # A-only, per the corrected definition


# ── Test 4 — dashboard endpoints reflect the newly ingested data ──

@pytest.mark.asyncio
async def test_dashboard_reflects_newly_ingested_data():
    csv_bytes = _build_nine_case_csv(include_unexpected_column=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}
        async with _preserve_app_state():
            analyze_job = await _analyze_and_get_job(client, headers, "capstone", "nine_case.csv", csv_bytes)
            assert analyze_job["status"] == "success", analyze_job.get("error_detail")
            token_id = analyze_job["result"]["token"]
            with _isolate_ml_paths(seed_live_period="99.9"):
                job = await _confirm_and_get_job(client, headers, "capstone", token_id)
            assert job["status"] == "success"

            summary = await client.get("/api/dashboard/summary", headers=headers)
            assert summary.status_code == 200
            body = summary.json()
            # 9 distinct students (StudentP1/F1/I1/R1/W1/C1/M1/U1/N1) — StudentR1 appears
            # in 2 rows (one per attempt) but is still 1 distinct student.
            assert body["total_students"] == 9
            assert body["total_subjects"] == 2  # TEST100 + TEST101


# ── Test 5 — retrain trigger fires ONLY on genuine new-period data ──

@pytest.mark.asyncio
async def test_retrain_trigger_same_period_vs_new_period():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        # ── Case A: same period as the seeded live model — must NOT retrain ──
        csv_bytes = _build_nine_case_csv(include_unexpected_column=False)  # max period 99.2
        async with _preserve_app_state():
            analyze_job = await _analyze_and_get_job(client, headers, "capstone", "same_period.csv", csv_bytes)
            assert analyze_job["status"] == "success", analyze_job.get("error_detail")
            token_id = analyze_job["result"]["token"]
            with _isolate_ml_paths(seed_live_period="99.2"):  # same as the data's latest period
                job_same = await _confirm_and_get_job(client, headers, "capstone", token_id)
        assert job_same["status"] == "success"
        assert job_same["result"]["retrain"]["triggered"] is False

        # ── Case B: genuinely new period — must retrain (candidate only) ──
        # Real-subject data, duplicating the CI-loaded real dataset's latest
        # period under a new period label, same technique
        # verify_dynamic_period_e2e.py already uses — a real retrain needs
        # real SAFE_SUBJECTS-eligible rows, which the fake TEST100/TEST101
        # subjects above are not.
        real_df = pd.read_csv(train_model.DATA_PATH)
        real_df.columns = [c.strip() for c in real_df.columns]
        periods = real_df["STUDYPERIOD"].apply(lambda x: str(round(float(x), 1)))
        real_latest = sorted(periods.unique(), key=float)[-1]
        source_rows = real_df[periods == real_latest].copy()
        new_period = str(round(float(real_latest) + 0.1, 1))
        synthetic_rows = source_rows.copy()
        synthetic_rows["STUDYPERIOD"] = new_period
        synthetic_full = pd.concat([real_df, synthetic_rows], ignore_index=True)
        buf = io.StringIO()
        synthetic_full.to_csv(buf, index=False)
        new_period_csv_bytes = buf.getvalue().encode()

        async with _preserve_app_state():
            analyze_job_b = await _analyze_and_get_job(client, headers, "capstone", "new_period.csv", new_period_csv_bytes)
            assert analyze_job_b["status"] == "success", analyze_job_b.get("error_detail")
            token_id_b = analyze_job_b["result"]["token"]
            with _isolate_ml_paths(seed_live_period=real_latest) as (_tmp_dir, isolated_registry_path):
                job_new = await _confirm_and_get_job(client, headers, "capstone", token_id_b)
                assert job_new["status"] == "success", job_new.get("error_detail")
                retrain = job_new["result"]["retrain"]
                assert retrain["triggered"] is True
                assert retrain["candidate_version"] is not None

                # ── Test 6 — candidate registered but NOT live ──
                with open(isolated_registry_path) as f:
                    isolated_registry = json.load(f)
                assert isolated_registry["live_version"] == "seed_v1", \
                    "registration must never change live_version — promotion stays manual"
                candidate_versions = {v["version"] for v in isolated_registry["versions"]}
                assert retrain["candidate_version"] in candidate_versions

        # Predictions still come from the previously-live model — the real,
        # unpatched serving model (loaded once at app startup, never reloaded
        # by ingestion/retrain) is completely untouched by any of the above.
        predict_res = await client.post(
            "/api/predict", headers=headers,
            json={
                "subject": "ICT104", "study_period": "25.2", "trimester_num": 25.2,
                "assess1_mark": 70.0, "assess1_weight": 50.0, "assess1_contribution": 35.0,
                "assess2_mark": 0.0, "assess2_weight": 0.0, "assess2_contribution": 0.0,
                "partial_weighted_score": 35.0, "partial_weight_coverage": 0.5,
                "num_assessments": 1, "total_weight_recorded": 50.0, "weight_complete": False,
                "assessments_used": [{"type": "TX", "mark_percent": 70.0, "weighting": 50.0}],
            },
        )
        assert predict_res.status_code == 200
        assert predict_res.json().get("prediction") in ("Pass", "Fail")

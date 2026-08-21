"""
EDAPT v2 — Chunked upload for large ingestion files
(POST /api/ingest/{kind}/batch/init, POST .../batch/{id}/chunk,
GET .../batch/{id}, GET /api/ingest/batches).

Replaces sending a whole capstone/attendance CSV as one multipart request.
Real motivating bug: a 125MB attendance CSV sent as a single POST sat
stuck "(pending)" in the browser for 500+ seconds and never completed,
even though a direct curl upload of a similarly sized file to the same
single-shot endpoint finished in well under two minutes and the CORS
preflight for the browser's own request succeeded instantly — something
about handling one huge request client-side, not the backend or network
path, was the problem. Splitting the upload into small sequential chunks
(see UploadBatch's docstring in app/db/models.py) sidesteps that failure
mode entirely and gives real per-chunk progress instead of one opaque
spinner.

Uses the same _login / _preserve_app_state helpers as
test_ingestion_e2e.py — a completed batch hands off to the exact same
AnalyzeJob/PendingIngest machinery those tests already cover, so these
tests focus on the chunking mechanics themselves (ordering, idempotent
retry, size validation) rather than re-testing analyze's own parsing.
"""

import io

import pandas as pd
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete

import app.main as main_mod
from app.db.models import UploadBatch
from app.main import app
from tests.test_ingestion_e2e import _login, _preserve_app_state


def _build_attendance_csv(n_rows=3) -> bytes:
    rows = [{
        "course": "ACC101", "location_code": "L1", "building": "B1", "room": "R1",
        "study_period_code": "T2", "year": 2026, "class_no": 1, "actv_no": 1,
        "cls_session_no": i, "attendance_code": "H", "STUDENTID_MASKED": "BatchTestStudent0",
    } for i in range(n_rows)]
    buf = io.StringIO()
    pd.DataFrame(rows).to_csv(buf, index=False)
    return buf.getvalue().encode()


@pytest.fixture
def small_chunk_size():
    """Patches the server's chunk size down so a small test CSV still
    splits into several real chunks, instead of needing a multi-MB payload
    just to exercise multi-chunk behavior at all."""
    original = main_mod.UPLOAD_CHUNK_MAX_BYTES
    main_mod.UPLOAD_CHUNK_MAX_BYTES = 40
    yield
    main_mod.UPLOAD_CHUNK_MAX_BYTES = original


async def _cleanup_batches():
    async with main_mod._AsyncSession() as db:
        await db.execute(delete(UploadBatch))
        await db.commit()


async def _upload_all_chunks(client, headers, kind, filename, content, chunk_size):
    init_res = await client.post(
        f"/api/ingest/{kind}/batch/init", headers=headers,
        json={"filename": filename, "total_size": len(content)},
    )
    assert init_res.status_code == 201, init_res.text
    init = init_res.json()
    batch_id = init["batch_id"]
    assert init["chunk_size"] == chunk_size
    expected_chunks = -(-len(content) // chunk_size)  # ceil division
    assert init["total_chunks"] == expected_chunks

    last = None
    for idx in range(expected_chunks):
        start = idx * chunk_size
        piece = content[start:start + chunk_size]
        res = await client.post(
            f"/api/ingest/{kind}/batch/{batch_id}/chunk",
            headers={**headers, "Content-Type": "application/octet-stream"},
            params={"chunk_index": idx}, content=piece,
        )
        assert res.status_code == 200, res.text
        last = res.json()
    return batch_id, last


@pytest.mark.asyncio
async def test_chunked_upload_completes_and_hands_off_to_analyze(small_chunk_size):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        async with _preserve_app_state():
            try:
                content = _build_attendance_csv(n_rows=5)
                assert len(content) > main_mod.UPLOAD_CHUNK_MAX_BYTES * 2, "test needs a genuine multi-chunk upload"

                batch_id, last = await _upload_all_chunks(
                    client, headers, "attendance", "batch_test.csv", content, main_mod.UPLOAD_CHUNK_MAX_BYTES,
                )
                assert last["status"] == "analyzing"
                assert last["analyze_job_id"]

                analyze_job = (await client.get(
                    f"/api/ingest/analyze-jobs/{last['analyze_job_id']}", headers=headers,
                )).json()
                assert analyze_job["status"] == "success", analyze_job.get("error_detail")
                assert analyze_job["result"]["row_count"] == 5

                status = (await client.get(f"/api/ingest/attendance/batch/{batch_id}", headers=headers)).json()
                assert status["status"] == "analyzing"
                assert status["received_chunks"] == status["total_chunks"]

                listing = (await client.get("/api/ingest/batches", headers=headers)).json()
                assert any(b["id"] == batch_id for b in listing["batches"])
            finally:
                await _cleanup_batches()


@pytest.mark.asyncio
async def test_retrying_the_just_received_chunk_is_idempotent(small_chunk_size):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        async with _preserve_app_state():
            try:
                content = _build_attendance_csv(n_rows=5)
                init = (await client.post(
                    "/api/ingest/attendance/batch/init", headers=headers,
                    json={"filename": "retry_test.csv", "total_size": len(content)},
                )).json()
                batch_id, chunk_size = init["batch_id"], init["chunk_size"]

                first = content[:chunk_size]
                r1 = await client.post(
                    f"/api/ingest/attendance/batch/{batch_id}/chunk",
                    headers={**headers, "Content-Type": "application/octet-stream"},
                    params={"chunk_index": 0}, content=first,
                )
                assert r1.status_code == 200
                assert r1.json()["received_chunks"] == 1

                # Re-POSTing chunk 0 again (simulating a client that sent it
                # but never saw the response) must succeed as a no-op, not
                # double-count it or re-append the bytes.
                r2 = await client.post(
                    f"/api/ingest/attendance/batch/{batch_id}/chunk",
                    headers={**headers, "Content-Type": "application/octet-stream"},
                    params={"chunk_index": 0}, content=first,
                )
                assert r2.status_code == 200
                assert r2.json()["received_chunks"] == 1
            finally:
                await _cleanup_batches()


@pytest.mark.asyncio
async def test_out_of_order_chunk_is_rejected(small_chunk_size):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        async with _preserve_app_state():
            try:
                content = _build_attendance_csv(n_rows=5)
                init = (await client.post(
                    "/api/ingest/attendance/batch/init", headers=headers,
                    json={"filename": "order_test.csv", "total_size": len(content)},
                )).json()
                batch_id, chunk_size = init["batch_id"], init["chunk_size"]

                # Skip straight to chunk 2 without ever sending 0 or 1.
                res = await client.post(
                    f"/api/ingest/attendance/batch/{batch_id}/chunk",
                    headers={**headers, "Content-Type": "application/octet-stream"},
                    params={"chunk_index": 2}, content=content[:chunk_size],
                )
                assert res.status_code == 409
                assert "Expected chunk 0" in res.json()["detail"]
            finally:
                await _cleanup_batches()


@pytest.mark.asyncio
async def test_size_mismatch_at_finalize_marks_batch_failed(small_chunk_size):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        async with _preserve_app_state():
            try:
                # Declare a total_size larger than what will actually be sent
                # — the single chunk below is short of that declared total,
                # so the assembled file's real size can never match it.
                declared_size = 200
                init = (await client.post(
                    "/api/ingest/attendance/batch/init", headers=headers,
                    json={"filename": "mismatch_test.csv", "total_size": declared_size},
                )).json()
                batch_id, chunk_size, total_chunks = init["batch_id"], init["chunk_size"], init["total_chunks"]

                content = _build_attendance_csv(n_rows=1)  # deliberately far short of declared_size
                last = None
                for idx in range(total_chunks):
                    start = idx * chunk_size
                    piece = content[start:start + chunk_size] or b"x"  # keep sending non-empty bytes
                    res = await client.post(
                        f"/api/ingest/attendance/batch/{batch_id}/chunk",
                        headers={**headers, "Content-Type": "application/octet-stream"},
                        params={"chunk_index": idx}, content=piece,
                    )
                    assert res.status_code == 200
                    last = res.json()
                assert last["status"] == "failed"
                assert "didn't match" in last["error_detail"]
            finally:
                await _cleanup_batches()


@pytest.mark.asyncio
async def test_batch_init_rejects_non_csv_and_oversized_declared_size():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}

        bad_ext = await client.post(
            "/api/ingest/attendance/batch/init", headers=headers,
            json={"filename": "data.xlsx", "total_size": 1000},
        )
        assert bad_ext.status_code == 400

        too_big = await client.post(
            "/api/ingest/attendance/batch/init", headers=headers,
            json={"filename": "huge.csv", "total_size": main_mod.MAX_ATTENDANCE_UPLOAD_BYTES + 1},
        )
        assert too_big.status_code == 400
        assert "exceeds" in too_big.json()["detail"]


@pytest.mark.asyncio
async def test_batch_endpoints_reject_lecturer():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        login = await client.post("/api/auth/login", json={"email": "user", "password": "Lect@2025!"})
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        res = await client.post(
            "/api/ingest/attendance/batch/init", headers=headers,
            json={"filename": "x.csv", "total_size": 100},
        )
        assert res.status_code == 403


@pytest.mark.asyncio
async def test_batch_init_rejects_unknown_kind():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}
        res = await client.post(
            "/api/ingest/nonsense/batch/init", headers=headers,
            json={"filename": "x.csv", "total_size": 100},
        )
        assert res.status_code == 400

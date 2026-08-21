"""
EDAPT v2 — Students-at-Risk bulk intervention logging and the risk email
template config.

Covers the "no real student email exists anywhere in this system" design:
POST /api/interventions/bulk only ever writes Intervention rows (never
sends anything), rendering the {{placeholder}} template per-target so each
row's notes reflects its own student/subject/period/risk_band rather than
one identical blob across every row.
"""

import contextlib

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete

import app.main as main_mod
from app.db.models import Intervention, RiskEmailTemplate
from app.main import app

TEST_STUDENT_IDS = ["RiskEmailTestStudent1", "RiskEmailTestStudent2"]


async def _login(client, email: str, password: str) -> str:
    res = await client.post("/api/auth/login", json={"email": email, "password": password})
    return res.json()["access_token"]


@contextlib.asynccontextmanager
async def _preserve_template_and_interventions():
    """Snapshot the singleton template row and restore it afterward, and
    delete any Intervention rows this test created for TEST_STUDENT_IDS —
    both are shared, cross-worker Postgres tables a stray test row would
    pollute for the real app too."""
    async with main_mod._AsyncSession() as db:
        row = await db.get(RiskEmailTemplate, 1)
        original = {"subject": row.subject, "body": row.body, "updated_by": row.updated_by}
    try:
        yield
    finally:
        async with main_mod._AsyncSession() as db:
            row = await db.get(RiskEmailTemplate, 1)
            row.subject, row.body, row.updated_by = (
                original["subject"], original["body"], original["updated_by"],
            )
            await db.execute(delete(Intervention).where(Intervention.student_id_masked.in_(TEST_STUDENT_IDS)))
            await db.commit()


@pytest.mark.asyncio
async def test_get_risk_email_template_returns_seeded_default():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.get("/api/risk-email-template", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert "{{student_id}}" in body["body"]
    assert "subject" in body and "updated_at" in body


@pytest.mark.asyncio
async def test_update_risk_email_template_admin_only():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await _login(client, "admin", "Admin@2025!")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        lect_token = await _login(client, "user", "Lect@2025!")
        lect_headers = {"Authorization": f"Bearer {lect_token}"}

        async with _preserve_template_and_interventions():
            # Lecturer cannot change the shared template.
            r_forbidden = await client.put(
                "/api/risk-email-template", headers=lect_headers,
                json={"subject": "nope", "body": "nope"},
            )
            assert r_forbidden.status_code == 403

            # Admin can, and the response is fully JSON-serializable and
            # correct right away — this is the exact path that used to
            # crash with sqlalchemy.exc.MissingGreenlet (reading the ORM
            # row's attributes after _append_audit_db's commit had
            # already expired them). Asserting on every field, not just
            # the status code, so a regression here fails loudly again.
            new_subject = "Updated subject {{subject_code}}"
            new_body = "Hi {{student_id}} — {{risk_band}} in {{subject_code}} ({{study_period}})"
            r = await client.put(
                "/api/risk-email-template", headers=admin_headers,
                json={"subject": new_subject, "body": new_body},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["subject"] == new_subject
            assert body["body"] == new_body
            assert body["updated_by"] == "admin"
            assert body["updated_at"]  # a real ISO timestamp, not None/missing

            # And it's actually persisted, not just echoed back.
            r_get = await client.get("/api/risk-email-template", headers=admin_headers)
            assert r_get.json()["subject"] == new_subject


@pytest.mark.asyncio
async def test_bulk_intervention_renders_template_per_target_and_scopes_by_subject():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await _login(client, "admin", "Admin@2025!")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        lect_token = await _login(client, "user", "Lect@2025!")  # subjects: ICT104, ICT201, ICT301
        lect_headers = {"Authorization": f"Bearer {lect_token}"}

        async with _preserve_template_and_interventions():
            r = await client.post(
                "/api/interventions/bulk", headers=admin_headers,
                json={
                    "action_type": "email sent",
                    "notes": "Hi {{student_id}} — {{risk_band}} in {{subject_code}} ({{study_period}})",
                    "targets": [
                        {
                            "student_id_masked": TEST_STUDENT_IDS[0], "subject_code": "ICT104",
                            "study_period": "25.3", "risk_band": "High Risk",
                        },
                        {
                            "student_id_masked": TEST_STUDENT_IDS[1], "subject_code": "ICT104",
                            "study_period": "25.3", "risk_band": "At Risk",
                        },
                    ],
                },
            )
            assert r.status_code == 201
            assert r.json()["created"] == 2

            r_list = await client.get(
                "/api/interventions", headers=admin_headers,
                params={"student_id_masked": TEST_STUDENT_IDS[0]},
            )
            rows = r_list.json()["interventions"]
            assert len(rows) == 1
            assert rows[0]["action_type"] == "email sent"
            # Placeholders resolved per-target, not left as literal {{...}}.
            assert rows[0]["notes"] == f"Hi {TEST_STUDENT_IDS[0]} — High Risk in ICT104 (25.3)"

            # A lecturer cannot bulk-log for a subject they aren't assigned to.
            r_forbidden = await client.post(
                "/api/interventions/bulk", headers=lect_headers,
                json={
                    "action_type": "email sent",
                    "targets": [{
                        "student_id_masked": "SomeOtherStudent", "subject_code": "NOT_MINE",
                        "study_period": "25.3",
                    }],
                },
            )
            assert r_forbidden.status_code == 403


@pytest.mark.asyncio
async def test_bulk_intervention_rejects_unknown_action_type():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.post(
            "/api/interventions/bulk", headers=headers,
            json={
                "action_type": "not a real action type",
                "targets": [{
                    "student_id_masked": TEST_STUDENT_IDS[0], "subject_code": "ICT104",
                    "study_period": "25.3",
                }],
            },
        )
    assert r.status_code == 422

"""
EDAPT v2 — Students-at-Risk bulk intervention logging and the risk email
template config.

Covers the "no real student email exists anywhere in this system" design:
POST /api/interventions/bulk only ever writes Intervention rows (never
sends anything), rendering the {{placeholder}} template per-target so each
row's notes reflects its own student/subject/period/risk_band rather than
one identical blob across every row.

RiskEmailTemplate is a real list (CRUD via /api/risk-email-templates), not
the single fixed-id row it used to be — an admin saves several named
templates and the Students at Risk page picks one from a dropdown.
"""

import contextlib

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete, select

import app.main as main_mod
from app.db.models import Intervention, RiskEmailTemplate
from app.main import app

TEST_STUDENT_IDS = ["RiskEmailTestStudent1", "RiskEmailTestStudent2"]


async def _login(client, email: str, password: str) -> str:
    res = await client.post("/api/auth/login", json={"email": email, "password": password})
    return res.json()["access_token"]


@contextlib.asynccontextmanager
async def _preserve_template_and_interventions():
    """Snapshot every existing template row (this table went from a
    singleton to a real list — see RiskEmailTemplate's docstring) and put
    the table back to exactly that state afterward: fields restored for
    any row a test edited, rows a test deleted re-inserted with their
    original id, rows a test created removed. Also deletes any
    Intervention rows this test created for TEST_STUDENT_IDS. Both are
    shared, cross-worker Postgres tables a stray test row would pollute
    for the real app too."""
    async with main_mod._AsyncSession() as db:
        result = await db.execute(select(RiskEmailTemplate))
        originals = {
            r.id: {"name": r.name, "subject": r.subject, "body": r.body, "updated_by": r.updated_by}
            for r in result.scalars().all()
        }
    try:
        yield
    finally:
        async with main_mod._AsyncSession() as db:
            result = await db.execute(select(RiskEmailTemplate))
            current_by_id = {r.id: r for r in result.scalars().all()}
            for tid, o in originals.items():
                row = current_by_id.get(tid)
                if row is not None:
                    row.name, row.subject, row.body, row.updated_by = (
                        o["name"], o["subject"], o["body"], o["updated_by"],
                    )
                else:
                    db.add(RiskEmailTemplate(id=tid, **o))
            for tid, row in current_by_id.items():
                if tid not in originals:
                    await db.delete(row)
            await db.execute(delete(Intervention).where(Intervention.student_id_masked.in_(TEST_STUDENT_IDS)))
            await db.commit()


@pytest.mark.asyncio
async def test_list_risk_email_templates_returns_seeded_default():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client, "admin", "Admin@2025!")
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.get("/api/risk-email-templates", headers=headers)
    assert r.status_code == 200
    templates = r.json()["templates"]
    assert len(templates) >= 1
    assert any("{{student_id}}" in t["body"] for t in templates)
    assert all({"id", "name", "subject", "body", "updated_at"} <= set(t) for t in templates)


@pytest.mark.asyncio
async def test_create_update_delete_risk_email_template_admin_only():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await _login(client, "admin", "Admin@2025!")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        lect_token = await _login(client, "user", "Lect@2025!")
        lect_headers = {"Authorization": f"Bearer {lect_token}"}

        async with _preserve_template_and_interventions():
            # Lecturer cannot create a template.
            r_forbidden = await client.post(
                "/api/risk-email-templates", headers=lect_headers,
                json={"name": "nope", "subject": "nope", "body": "nope"},
            )
            assert r_forbidden.status_code == 403

            # Admin can, and the response is fully JSON-serializable and
            # correct right away — this is the exact path that used to
            # crash with sqlalchemy.exc.MissingGreenlet (reading the ORM
            # row's attributes after _append_audit_db's commit had
            # already expired them). Asserting on every field, not just
            # the status code, so a regression here fails loudly again.
            new_name    = "Second Notice"
            new_subject = "Second notice {{subject_code}}"
            new_body    = "Hi {{student_id}} — {{risk_band}} in {{subject_code}} ({{study_period}})"
            r_create = await client.post(
                "/api/risk-email-templates", headers=admin_headers,
                json={"name": new_name, "subject": new_subject, "body": new_body},
            )
            assert r_create.status_code == 201
            created = r_create.json()
            assert created["name"] == new_name
            assert created["subject"] == new_subject
            assert created["updated_by"] == "admin"
            assert created["created_at"] and created["updated_at"]
            template_id = created["id"]

            # It's actually persisted, not just echoed back.
            r_list = await client.get("/api/risk-email-templates", headers=admin_headers)
            assert any(t["id"] == template_id and t["name"] == new_name for t in r_list.json()["templates"])

            # Lecturer cannot update or delete it.
            assert (await client.put(
                f"/api/risk-email-templates/{template_id}", headers=lect_headers,
                json={"name": "nope", "subject": "nope", "body": "nope"},
            )).status_code == 403
            assert (await client.delete(
                f"/api/risk-email-templates/{template_id}", headers=lect_headers,
            )).status_code == 403

            # Admin can update it.
            edited_name = "Second Notice (Edited)"
            r_update = await client.put(
                f"/api/risk-email-templates/{template_id}", headers=admin_headers,
                json={"name": edited_name, "subject": new_subject, "body": new_body},
            )
            assert r_update.status_code == 200
            assert r_update.json()["name"] == edited_name

            # Admin can delete it, since another template (the seeded default) still exists.
            r_delete = await client.delete(f"/api/risk-email-templates/{template_id}", headers=admin_headers)
            assert r_delete.status_code == 200
            r_list_after = await client.get("/api/risk-email-templates", headers=admin_headers)
            assert not any(t["id"] == template_id for t in r_list_after.json()["templates"])


@pytest.mark.asyncio
async def test_cannot_delete_last_remaining_risk_email_template():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await _login(client, "admin", "Admin@2025!")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        async with _preserve_template_and_interventions():
            # Reduce to exactly one template (deleting all originals but the
            # first), then confirm that last one is protected from deletion.
            # _preserve_template_and_interventions re-inserts every original
            # row afterward regardless of what this test does to them.
            async with main_mod._AsyncSession() as db:
                ids = [row[0] for row in (await db.execute(select(RiskEmailTemplate.id))).all()]
            for extra_id in ids[1:]:
                await client.delete(f"/api/risk-email-templates/{extra_id}", headers=admin_headers)

            r = await client.delete(f"/api/risk-email-templates/{ids[0]}", headers=admin_headers)
            assert r.status_code == 400
            r_list = await client.get("/api/risk-email-templates", headers=admin_headers)
            assert len(r_list.json()["templates"]) == 1


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

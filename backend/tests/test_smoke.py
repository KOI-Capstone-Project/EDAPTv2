"""EDAPT v2 — Smoke tests for the FastAPI app."""

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_login_success():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/auth/login",
            json={"email": "admin", "password": "Admin@2025!"},
        )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "token_type" in body


@pytest.mark.asyncio
async def test_login_wrong_password():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/auth/login",
            json={"email": "admin", "password": "definitely_wrong_password"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_brute_force():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(6):
            response = await client.post(
                "/api/auth/login",
                json={"email": "bruteforce@smoke.test", "password": "wrong"},
            )
    assert response.status_code == 429


@pytest.mark.asyncio
async def test_predict_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/predict",
            json={"subject": "ICT104", "assess1_mark": 50.0},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ingest_preview_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/ingest/preview")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_predict_recomputes_partial_score_server_side():
    """
    Regression test for a train/serve mismatch: the ML model was trained on a
    top-2-highest-weighted-assessment definition of partial_weighted_score
    (train_model.py's build_early_features()), but the frontend used to send a
    sum across ALL entered assessments instead — silently feeding the model a
    feature value outside its training distribution for any 3+ assessment
    scenario. /api/predict must ignore whatever partial_weighted_score /
    partial_weight_coverage the client sends and always recompute both
    server-side (predictor.compute_partial_score), so a stale or buggy client
    can never reintroduce this mismatch.
    """
    assessments_used = [
        {"type": "A", "mark_percent": 100.0, "weighting": 50.0},
        {"type": "B", "mark_percent": 100.0, "weighting": 30.0},
        {"type": "C", "mark_percent": 100.0, "weighting": 20.0},
    ]
    # "Old buggy frontend" value: sum of ALL three contributions, not just the top 2.
    buggy_client_partial_score = sum(a["mark_percent"] * a["weighting"] / 100 for a in assessments_used)
    buggy_client_coverage      = sum(a["weighting"] for a in assessments_used) / 100
    # Correct value: only the two heaviest-weighted items (A=50, B=30) count.
    correct_partial_score = 100.0 * 50.0 / 100 + 100.0 * 30.0 / 100
    assert buggy_client_partial_score != correct_partial_score  # sanity check: scenario must actually diverge

    body = {
        "subject":                "ICT205",
        "study_period":           "25.2",
        "trimester_num":          25.2,
        "assess1_mark":           100.0,
        "assess1_weight":         50.0,
        "assess1_contribution":   50.0,
        "assess2_mark":           100.0,
        "assess2_weight":         30.0,
        "assess2_contribution":   30.0,
        "partial_weighted_score":  buggy_client_partial_score,
        "partial_weight_coverage": buggy_client_coverage,
        "num_assessments":        3,
        "total_weight_recorded":  100.0,
        "weight_complete":        True,
        "assessments_used":       assessments_used,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        login = await client.post(
            "/api/auth/login",
            json={"email": "admin", "password": "Admin@2025!"},
        )
        token = login.json()["access_token"]
        response = await client.post(
            "/api/predict",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data.get("prediction_available", True) is not False
    assert data["partial_weighted_score"] == pytest.approx(correct_partial_score)
    assert data["partial_weighted_score"] != pytest.approx(buggy_client_partial_score)


async def _login(client) -> str:
    login = await client.post(
        "/api/auth/login",
        json={"email": "admin", "password": "Admin@2025!"},
    )
    return login.json()["access_token"]


def _predict_body(subject: str, assessments_used: list, study_period: str = "25.2") -> dict:
    """Minimal valid PredictRequest body — assess1/2 fields are only used by
    the complete-record path (routing itself is driven by assessments_used'
    total weighting, computed server-side), so any placeholder values here
    that satisfy the schema are fine for the partial/insufficient tests."""
    return {
        "subject":                subject,
        "study_period":           study_period,
        "trimester_num":          float(study_period),
        "assess1_mark":           0.0,
        "assess1_weight":         0.0,
        "assess1_contribution":   0.0,
        "assess2_mark":           0.0,
        "assess2_weight":         0.0,
        "assess2_contribution":   0.0,
        "partial_weighted_score":  0.0,
        "partial_weight_coverage": 0.0,
        "num_assessments":        len(assessments_used),
        "total_weight_recorded":  sum(a["weighting"] for a in assessments_used),
        "weight_complete":        False,
        "assessments_used":       assessments_used,
    }


@pytest.mark.asyncio
async def test_predict_complete_record_routes_to_main_model():
    """
    Regression test protecting the existing baseline: a complete record
    (cumulative weighting == 100%) must route to best_model.pkl exactly as
    before — same model_name, no "mid-term estimate" label. This is the
    behaviour that must remain strictly unchanged by the coverage-based
    routing added on top of it.
    """
    assessments_used = [
        {"type": "A", "mark_percent": 90.0, "weighting": 60.0},
        {"type": "B", "mark_percent": 80.0, "weighting": 40.0},
    ]  # 60 + 40 = 100% coverage

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        response = await client.post(
            "/api/predict",
            json=_predict_body("ICT205", assessments_used),
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data.get("prediction_available", True) is not False
    assert data["model_name"] == "XGBoost + Random Forest Ensemble"
    assert "simulated" not in data["model_name"].lower()
    assert data.get("estimate_type") is None


@pytest.mark.asyncio
async def test_predict_partial_record_routes_to_simulated_model():
    """
    A genuinely partial record (50-99% coverage — here 60%) must route to
    best_model_simulated_progress.pkl and be clearly labelled as a mid-term
    estimate, not presented identically to a complete-record prediction.
    """
    assessments_used = [
        {"type": "A", "mark_percent": 80.0, "weighting": 40.0},
        {"type": "B", "mark_percent": 70.0, "weighting": 20.0},
    ]  # 40 + 20 = 60% coverage

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        response = await client.post(
            "/api/predict",
            json=_predict_body("ICT205", assessments_used),
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data.get("prediction_available", True) is not False
    assert "simulated" in data["model_name"].lower()
    assert data.get("estimate_type") == "mid-term estimate"
    # Cumulative sum of ALL items (not top-2-only): 80*40/100 + 70*20/100 = 46.0
    assert data["partial_weighted_score"] == pytest.approx(46.0)


@pytest.mark.asyncio
async def test_predict_insufficient_coverage_returns_no_risk_band():
    """
    Below 50% coverage, no model should be called at all — the response must
    be a coverage gate (coverage_status: insufficient_data), distinct from
    the unreliable-subject data-quality gate even though both use
    prediction_available: False.
    """
    assessments_used = [
        {"type": "A", "mark_percent": 80.0, "weighting": 20.0},
    ]  # 20% coverage

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        response = await client.post(
            "/api/predict",
            json=_predict_body("ICT205", assessments_used),
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["prediction_available"] is False
    assert data.get("coverage_status") == "insufficient_data"
    assert "risk_band" not in data
    assert "Head of Technology" not in data["message"]  # distinct from the unreliable-subject message


@pytest.mark.asyncio
async def test_predict_shap_explanation_matches_live_model():
    """
    The SHAP explanation returned by /api/predict must (a) come from the
    exact model version currently live in the registry — not a stale
    in-memory copy from a previous version — and (b) sum back to the
    probability it's explaining, not just look plausible. Checked
    separately for the complete-record model and the simulated-progress
    model (predict_partial()), since they're different fitted model
    objects with independently-built SHAP explainers (see explain.py).
    """
    from app.ml.model_registry import load_registry, get_live_entry
    from app.ml import predictor

    # ── complete-record path ────────────────────────────────────────────
    assessments_used = [
        {"type": "A", "mark_percent": 90.0, "weighting": 60.0},
        {"type": "B", "mark_percent": 80.0, "weighting": 40.0},
    ]  # 100% coverage
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        response = await client.post(
            "/api/predict",
            json=_predict_body("ICT205", assessments_used),
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200
    data = response.json()

    live_entry = get_live_entry(load_registry())
    assert data["model_version"] == live_entry["version"], (
        "SHAP-bearing prediction's model_version doesn't match the registry's "
        "current live version — the explanation would be for the wrong model."
    )

    se = data["shap_explanation"]
    assert se is not None
    assert se["sum_check_ok"] is True
    assert se["sum_check_delta"] < 0.05
    reconstructed = se["base_value"] + sum(f["contribution"] for f in se["all_factors"])
    assert reconstructed == pytest.approx(se["predicted_pass_probability"], abs=0.05)
    # what the explanation reconstructs must match what the user is actually shown
    assert data["probability"] == pytest.approx(se["predicted_pass_probability"], abs=0.15)
    assert len(se["top_factors"]) == 3
    assert all(f["feature"] in predictor._PACKAGE["features"] for f in se["all_factors"])

    # ── simulated-progress (partial-record) path — a genuinely different
    #    model object, independently verified ──────────────────────────
    partial_assessments = [
        {"type": "A", "mark_percent": 80.0, "weighting": 40.0},
        {"type": "B", "mark_percent": 70.0, "weighting": 20.0},
    ]  # 60% coverage
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        response = await client.post(
            "/api/predict",
            json=_predict_body("ICT205", partial_assessments),
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200
    data_partial = response.json()
    assert data_partial["estimate_type"] == "mid-term estimate"
    assert data_partial["model_version"] == predictor.SIM_MODEL_VERSION

    se_partial = data_partial["shap_explanation"]
    assert se_partial is not None
    assert se_partial["sum_check_ok"] is True
    assert se_partial["sum_check_delta"] < 0.05
    reconstructed_partial = se_partial["base_value"] + sum(f["contribution"] for f in se_partial["all_factors"])
    assert reconstructed_partial == pytest.approx(se_partial["predicted_pass_probability"], abs=0.05)
    assert data_partial["probability"] == pytest.approx(se_partial["predicted_pass_probability"], abs=0.15)

    # Same explanation methodology, but genuinely independent numbers — not
    # the complete-record explanation reused/mislabelled for the partial one.
    assert se["method"] == se_partial["method"]
    assert se["all_factors"] != se_partial["all_factors"]


@pytest.mark.asyncio
async def test_predict_partial_risk_band_never_contradicts_prediction():
    """
    Regression test for a real, reported bug: a screenshot showed
    probability=73.1 (green, "Safe" risk band) directly above the label
    "Fail" for the same mid-term-estimate prediction. Root cause: predict()
    and predict_partial() use different, honestly-validated decision
    thresholds (0.50 vs 0.25), but risk_band used to be a hardcoded 65/40
    split shared by both — since (1 - 0.25) * 100 = 75 > 65, any
    probability in [65, 75) was "Fail" by threshold and "Safe" by band.

    Reproduces the exact reported case (ICT101/25.1, ME 45/50 -> 90% on a
    50%-weighted item, mid-term estimate) and asserts the specific
    contradiction is gone, then sweeps the whole dead-zone range to confirm
    the invariant holds generally, not just for this one input.
    """
    assessments_used = [{"type": "ME", "mark_percent": 90.0, "weighting": 50.0}]  # 45/50 -> 90%, 50% coverage

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        response = await client.post(
            "/api/predict",
            json=_predict_body("ICT101", assessments_used, study_period="25.1"),
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["estimate_type"] == "mid-term estimate"
    # In the previously-dangerous 65-75% band the exact reported case landed
    # in (73.1%) — not asserting the exact figure, since it can shift
    # slightly across retrains; what matters is it's still in that band and
    # still doesn't contradict.
    assert 65 <= data["probability"] < 76
    # The bug: this used to be risk_band == "Safe" simultaneously with prediction == "Fail".
    assert not (data["risk_band"] == "Safe" and data["prediction"] == "Fail")

    # General invariant, not just this one input: sweep a range of marks that
    # cross the old dead zone (probability roughly 60-80%) and confirm "Safe"
    # and "Fail" never co-occur for any of them.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        for mark in (80, 83, 85, 87, 89, 90, 92, 95, 98):
            resp = await client.post(
                "/api/predict",
                json=_predict_body("ICT101", [{"type": "ME", "mark_percent": float(mark), "weighting": 50.0}]),
                headers={"Authorization": f"Bearer {token}"},
            )
            d = resp.json()
            assert not (d["risk_band"] == "Safe" and d["prediction"] == "Fail"), \
                f"mark={mark}: probability={d.get('probability')} prediction={d.get('prediction')} risk_band={d.get('risk_band')}"


def test_compute_risk_band_never_contradicts_threshold():
    """
    Pure unit-level proof of the same invariant, independent of any live
    server call: for ANY probability and ANY threshold (not just today's
    0.50/0.25), risk_band == "Safe" must never coincide with what the
    threshold itself would call "Fail" (proba_fail = 1 - probability/100
    >= threshold). Sweeps the full 0-100 range at several threshold values,
    including ones neither model currently uses, so this can't silently
    regress if a future retrain shifts FAIL_THRESHOLD.
    """
    from app.ml.predictor import _compute_risk_band

    for threshold in (0.10, 0.25, 0.30, 0.50, 0.55):
        for probability in range(0, 101):
            band = _compute_risk_band(float(probability), threshold)
            proba_fail = 1 - probability / 100
            would_be_fail = proba_fail >= threshold
            assert not (band == "Safe" and would_be_fail), \
                f"threshold={threshold} probability={probability}: band=Safe but would be Fail"

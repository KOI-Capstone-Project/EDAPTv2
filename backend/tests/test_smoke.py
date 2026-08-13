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


# ── Roster serving path ──────────────────────────────────────────────────────
# Every other prediction test above posts hand-built assessments_used to
# /api/predict, so they exercise the client-supplies-everything path only.
# NOTHING covered the roster endpoint, where the SERVER assembles features
# from stored data (_DATA marks + _ATTENDANCE lookups) before calling the
# model. That blind spot let a real outage run undetected: after an
# 11-feature (attendance-using) model went live, the roster endpoint was
# still calling the model without attendance_rate, so every row came back
# probability=null while the whole suite stayed green. These two tests
# close that gap — they assert real predictions come back, not just HTTP 200.

def _first_subject_period_with_data():
    """Pick a real subject+period from live data rather than hardcoding one,
    so this test doesn't rot when the dataset is refreshed."""
    from app.main import _DATA
    df = _DATA.dropna(subset=["MARKPERCENT"])
    grp = df.groupby(["SUBJECTCODE", "STUDYPERIOD"]).size().sort_values(ascending=False)
    for (subject, period), _ in grp.items():
        from app.main import _subject_reliability_category
        if _subject_reliability_category(subject) != "unreliable":
            return subject, period
    raise AssertionError("no usable subject/period found in the loaded dataset")


@pytest.mark.asyncio
async def test_roster_complete_record_returns_real_predictions_not_nulls():
    """The roster's complete-record tier must return actual probabilities.

    Regression test for a real outage: a null probability here means the
    server-side feature assembly failed (e.g. a feature the live model
    requires wasn't passed), which the endpoint swallows into
    probability=None rather than raising.
    """
    subject, period = _first_subject_period_with_data()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        response = await client.get(
            f"/api/subjects/{subject}/roster",
            params={"study_period": period},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    rows = payload.get("roster", payload) if isinstance(payload, dict) else payload
    assert isinstance(rows, list) and rows, f"roster returned no rows for {subject}/{period}"

    scorable = [r for r in rows if r.get("coverage_status") != "insufficient_data"]
    assert scorable, "no scorable rows — cannot verify predictions are being produced"
    scored = [r for r in scorable if r.get("probability") is not None]
    assert scored, (
        f"every scorable roster row came back with probability=None for "
        f"{subject}/{period} — the server-side prediction path is broken even "
        f"though the endpoint returned HTTP 200"
    )
    assert len(scored) == len(scorable), (
        f"only {len(scored)}/{len(scorable)} scorable rows got a probability"
    )
    r = scored[0]
    assert 0.0 <= r["probability"] <= 100.0
    assert r["prediction"] in {"Pass", "Fail"}
    assert r["risk_band"] in {"Safe", "At Risk", "High Risk"}


@pytest.mark.asyncio
async def test_roster_midterm_tier_returns_real_predictions_not_nulls():
    """Same guarantee for the mid-term tier, reached via simulate_progress.

    This tier was silently broken for longer than the complete-record one —
    it needs its own coverage, since it uses a different model, a different
    feature-assembly path (coverage-truncated attendance) and a different
    threshold.
    """
    subject, period = _first_subject_period_with_data()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        response = await client.get(
            f"/api/subjects/{subject}/roster",
            params={"study_period": period, "simulate_progress": 60},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    rows = payload.get("roster", payload) if isinstance(payload, dict) else payload
    midterm = [r for r in rows if r.get("estimate_type") == "mid-term estimate"]
    assert midterm, "simulate_progress produced no mid-term rows to check"
    scored = [r for r in midterm if r.get("probability") is not None]
    assert scored, (
        f"every mid-term roster row came back with probability=None for "
        f"{subject}/{period} — the mid-term serving path is broken despite HTTP 200"
    )
    assert len(scored) == len(midterm), (
        f"only {len(scored)}/{len(midterm)} mid-term rows got a probability"
    )


# ── Cross-endpoint agreement ────────────────────────────────────────────────
# The two tests above prove each endpoint works on its own. They cannot catch
# the two endpoints being individually fine but disagreeing with each other —
# which is exactly what happened: /api/predict ignored req.student_id and used
# the SUBJECT AVERAGE attendance rate (0.6220) for a real student whose own
# rate the roster correctly used (0.6923). Same person, two numbers, depending
# which screen you opened. Same class of bug as the Fail/Safe contradiction.

def _student_with_distinct_attendance():
    """Find a real complete-record enrolment whose own attendance rate differs
    materially from its subject average, so 'used the student's value' and
    'used the subject average' are actually distinguishable. Derived from live
    data rather than hardcoded so it survives a dataset refresh — the original
    reported case was Student0 / ACC705 / 23.2 (own 0.6923, subject avg 0.6220).
    """
    from app.main import (_DATA, _subject_reliability_category,
                          _student_full_attendance_rate,
                          _subject_average_attendance_rate, _period_total_weight)

    df = _DATA.dropna(subset=["MARKPERCENT"])
    for (student_id, subject, period), grp in df.groupby(
        ["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"]
    ):
        if _subject_reliability_category(subject) == "unreliable":
            continue
        total = _period_total_weight(subject, period)
        recorded = grp.drop_duplicates(subset=["ASSESSMENTTYPECODE"])["WEIGHTING"].sum()
        if not total or recorded < total:          # complete-record tier only
            continue
        own = _student_full_attendance_rate(str(student_id), subject, period)
        avg = _subject_average_attendance_rate(subject)
        if own is None or avg is None or abs(own - avg) < 0.02:
            continue
        return str(student_id), subject, period, own, avg, grp
    raise AssertionError(
        "no enrolment found whose own attendance rate differs from its subject "
        "average — cannot distinguish the two behaviours"
    )


@pytest.mark.asyncio
async def test_predict_and_roster_agree_on_a_real_students_attendance():
    """/api/predict and the roster must resolve attendance identically.

    Regression test for a real inconsistency: for the same real student,
    the roster used that student's own attendance rate while /api/predict
    fell back to the subject average, because /api/predict never looked at
    req.student_id. Both now go through _resolve_attendance_rate().

    Asserts the fallback is genuinely a fallback: a student who HAS an
    attendance record must never be scored against the subject average, and
    attendance_rate_is_default must be False for them.
    """
    student_id, subject, period, own_rate, subject_avg, grp = \
        _student_with_distinct_attendance()

    grp_sorted = grp.sort_values("WEIGHTING", ascending=False).reset_index(drop=True)
    assessments_used = [
        {"type": str(r["ASSESSMENTTYPECODE"]),
         "mark_percent": float(r["MARKPERCENT"]),
         "weighting": float(r["WEIGHTING"])}
        for _, r in grp_sorted.iterrows()
    ]
    a1 = grp_sorted.iloc[0]
    a1_mark, a1_weight = float(a1["MARKPERCENT"]), float(a1["WEIGHTING"])
    if len(grp_sorted) > 1:
        a2 = grp_sorted.iloc[1]
        a2_mark, a2_weight = float(a2["MARKPERCENT"]), float(a2["WEIGHTING"])
    else:
        a2_mark, a2_weight = 0.0, 0.0

    body = {
        "student_id":              student_id,
        "subject":                 subject,
        "study_period":            period,
        "trimester_num":           float(period),
        "assess1_mark":            a1_mark,
        "assess1_weight":          a1_weight,
        "assess1_contribution":    a1_mark * a1_weight / 100,
        "assess2_mark":            a2_mark,
        "assess2_weight":          a2_weight,
        "assess2_contribution":    a2_mark * a2_weight / 100,
        "partial_weighted_score":  a1_mark * a1_weight / 100 + a2_mark * a2_weight / 100,
        "partial_weight_coverage": (a1_weight + a2_weight) / 100,
        "num_assessments":         len(assessments_used),
        "total_weight_recorded":   sum(a["weighting"] for a in assessments_used),
        "weight_complete":         True,
        "assessments_used":        assessments_used,
        # deliberately NOT sending attendance_rate — the server must resolve it
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        headers = {"Authorization": f"Bearer {token}"}
        roster_resp = await client.get(
            f"/api/subjects/{subject}/roster",
            params={"study_period": period}, headers=headers,
        )
        predict_resp = await client.post("/api/predict", json=body, headers=headers)

    assert roster_resp.status_code == 200, roster_resp.text
    assert predict_resp.status_code == 200, predict_resp.text

    rows = roster_resp.json()["roster"]
    row = next((r for r in rows if r["student_id"] == student_id), None)
    assert row is not None, f"{student_id} missing from the {subject}/{period} roster"
    predict_data = predict_resp.json()

    assert row["attendance_rate_used"] == pytest.approx(own_rate, abs=1e-6), (
        f"roster scored {student_id} with {row['attendance_rate_used']} instead of "
        f"that student's own attendance rate {own_rate}"
    )
    assert predict_data["attendance_rate_used"] == pytest.approx(own_rate, abs=1e-6), (
        f"/api/predict scored {student_id} with "
        f"{predict_data['attendance_rate_used']} instead of that student's own "
        f"rate {own_rate} (subject average is {subject_avg}) — the endpoints have "
        f"drifted apart again"
    )
    assert predict_data["attendance_rate_used"] != pytest.approx(subject_avg, abs=1e-6), (
        "/api/predict fell back to the subject average for a student who has a "
        "real attendance record"
    )
    assert row["attendance_rate_used"] == pytest.approx(
        predict_data["attendance_rate_used"], abs=1e-9
    ), "the two endpoints report different attendance for the same student"
    assert predict_data["attendance_rate_is_default"] is False, (
        "attendance_rate_is_default must be False when a real per-student rate "
        "was used — the frontend shows a 'defaulted' notice based on this flag"
    )


# ── Interventions ───────────────────────────────────────────────────────────

async def _create_user(client, token, email, subjects, role="Lecturer"):
    await client.delete(f"/api/users/{email}", headers={"Authorization": f"Bearer {token}"})
    return await client.post(
        "/api/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": email, "password": "Probe@2025!", "name": "Probe User",
              "role": role, "subjects": subjects},
    )


@pytest.mark.asyncio
async def test_interventions_are_scoped_to_a_lecturers_own_subjects():
    """A lecturer must not see interventions logged for subjects they don't teach.

    Uses two throwaway lecturers with DISJOINT subject lists, so "can't see it"
    is unambiguous rather than an accident of overlapping assignments. Scoping
    is applied in the SQL query, so the other lecturer's rows are never loaded.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        admin = await _login(client)
        A = {"Authorization": f"Bearer {admin}"}

        r1 = await _create_user(client, admin, "iv_lect1@probe.test", ["ICT104"])
        r2 = await _create_user(client, admin, "iv_lect2@probe.test", ["ACC705"])
        assert r1.status_code == 201, r1.text
        assert r2.status_code == 201, r2.text

        tok1 = (await client.post("/api/auth/login", json={
            "email": "iv_lect1@probe.test", "password": "Probe@2025!"})).json()["access_token"]
        tok2 = (await client.post("/api/auth/login", json={
            "email": "iv_lect2@probe.test", "password": "Probe@2025!"})).json()["access_token"]
        L1 = {"Authorization": f"Bearer {tok1}"}
        L2 = {"Authorization": f"Bearer {tok2}"}

        try:
            created = await client.post("/api/interventions", headers=L1, json={
                "student_id_masked": "Student0", "subject_code": "ICT104",
                "study_period": "25.2", "action_type": "meeting scheduled",
                "notes": "scoping probe"})
            assert created.status_code == 201, created.text
            iid = created.json()["id"]

            # owner sees it
            own = await client.get("/api/interventions", headers=L1)
            assert iid in [i["id"] for i in own.json()["interventions"]]

            # the other lecturer must NOT
            other = await client.get("/api/interventions", headers=L2)
            assert iid not in [i["id"] for i in other.json()["interventions"]], (
                "a lecturer can see an intervention for a subject they are not assigned"
            )

            # ...and cannot reach it by asking for that subject explicitly
            probe = await client.get("/api/interventions", headers=L2,
                                     params={"subject_code": "ICT104"})
            assert probe.status_code == 403

            # admin sees everything
            adm = await client.get("/api/interventions", headers=A)
            assert iid in [i["id"] for i in adm.json()["interventions"]]

            # writing to someone else's subject is refused
            denied = await client.post("/api/interventions", headers=L2, json={
                "student_id_masked": "Student0", "subject_code": "ICT104",
                "study_period": "25.2", "action_type": "email sent"})
            assert denied.status_code == 403

            # only whitelisted action types
            bad = await client.post("/api/interventions", headers=L1, json={
                "student_id_masked": "Student0", "subject_code": "ICT104",
                "study_period": "25.2", "action_type": "not a real action type"})
            assert bad.status_code == 422
        finally:
            for e in ("iv_lect1@probe.test", "iv_lect2@probe.test"):
                await client.delete(f"/api/users/{e}", headers=A)


# ── Actionable ("what would help most") factor selection ────────────────────

def test_actionable_factor_skips_larger_non_actionable_factors_on_real_shap():
    """The ranking must skip bigger non-actionable factors, on REAL SHAP output.

    Not the trivial case: this asserts that a harmful factor LARGER in
    magnitude than the chosen one exists and was deliberately excluded. On the
    current live model the biggest harmful factors for a typical student are
    PARTIAL_WEIGHT_COVERAGE and SUBJECT_DIFFICULTY — neither of which a student
    can act on — so a naive "largest negative SHAP value" implementation would
    tell a lecturer to fix the subject's difficulty.
    """
    from app.ml.actionable import (top_actionable_factor, excluded_factor_summary,
                                   is_actionable)
    from app.ml import predictor

    result = predictor.predict(
        subject="ACC705", study_period="23.2", trimester_num=23.2,
        assess1_mark=46.0, assess1_weight=50.0, assess1_contribution=23.0,
        assess2_mark=76.0, assess2_weight=30.0, assess2_contribution=22.8,
        partial_weighted_score=45.8, partial_weight_coverage=0.8,
        num_assessments=3, total_weight_recorded=100.0, weight_complete=True,
        assessments_used=[
            {"type": "FE", "mark_percent": 46.0, "weighting": 50.0},
            {"type": "DA", "mark_percent": 76.0, "weighting": 30.0},
            {"type": "ME", "mark_percent": 20.0, "weighting": 20.0},
        ],
        attendance_rate=0.6923,
    )
    shap = result["shap_explanation"]
    chosen = top_actionable_factor(shap)
    excluded = excluded_factor_summary(shap)

    assert chosen is not None, "no actionable factor found on a real prediction"
    assert is_actionable(chosen["feature"])
    assert chosen["contribution"] < 0, "recommended acting on a factor that is helping"

    # The point of the test: something worse was skipped on purpose.
    bigger = [e for e in excluded if e["contribution"] < chosen["contribution"]]
    assert bigger, (
        "this case no longer exercises the exclusion — no non-actionable factor "
        "outranks the chosen one, so the test would pass even with the filter removed"
    )

    # And the naive implementation would have picked a different, wrong answer.
    worst_overall = min(shap["all_factors"], key=lambda f: f["contribution"])
    assert not is_actionable(worst_overall["feature"])
    assert worst_overall["feature"] != chosen["feature"]


def test_actionable_factor_never_recommends_a_demographic_feature():
    """Forward-compatible guard.

    No demographic feature is in either model's feature set today — verified
    against predictor._PACKAGE["features"] below — so this case cannot be found
    in real output and is constructed deliberately. It fixes the behaviour for
    the day someone adds one: a demographic feature must never be surfaced as
    something a student should improve, no matter how large its SHAP value.
    """
    from app.ml.actionable import top_actionable_factor, is_actionable
    from app.ml import predictor

    for feats in (predictor._PACKAGE["features"], predictor._SIM_PACKAGE["features"]):
        assert not [f for f in feats if any(
            s in f.upper() for s in ("GENDER", "AGEGROUP", "COUNTRY", "ETHNIC"))], (
            "a demographic feature entered the model's feature set — the "
            "fairness implications need a deliberate decision, not a silent pass"
        )

    synthetic = {"all_factors": [
        # deliberately the largest magnitude in the list, and negative
        {"feature": "GENDERCODE",      "value": 1.0,  "contribution": -40.0, "direction": "Fail"},
        {"feature": "AGEGROUP",        "value": 2.0,  "contribution": -30.0, "direction": "Fail"},
        {"feature": "COUNTRY_MASKED",  "value": 7.0,  "contribution": -25.0, "direction": "Fail"},
        {"feature": "SUBJECT_DIFFICULTY", "value": 0.4, "contribution": -20.0, "direction": "Fail"},
        {"feature": "ATTENDANCE_RATE", "value": 0.55, "contribution":  -2.0, "direction": "Fail"},
    ]}
    chosen = top_actionable_factor(synthetic)

    assert chosen is not None
    assert chosen["feature"] == "ATTENDANCE_RATE", (
        f"expected the only actionable factor, got {chosen['feature']}"
    )
    for demographic in ("GENDERCODE", "AGEGROUP", "COUNTRY_MASKED"):
        assert not is_actionable(demographic)
    # renamed variants must still be caught
    for variant in ("STUDENT_GENDER", "AGE_GROUP_BUCKET", "COUNTRY_OF_ORIGIN"):
        assert not is_actionable(variant)


def test_actionable_factor_returns_none_when_nothing_actionable_is_harmful():
    """A student whose actionable factors are all helping gets no recommendation
    rather than a manufactured one."""
    from app.ml.actionable import top_actionable_factor
    assert top_actionable_factor({"all_factors": [
        {"feature": "ATTENDANCE_RATE", "value": 0.99, "contribution": +5.0, "direction": "Pass"},
        {"feature": "ASSESS1_MARK",    "value": 90.0, "contribution": +3.0, "direction": "Pass"},
        {"feature": "SUBJECT_DIFFICULTY", "value": 0.4, "contribution": -9.0, "direction": "Fail"},
    ]}) is None
    assert top_actionable_factor(None) is None


# ── Model health dashboard (admin-only, read-only) ──────────────────────────

@pytest.mark.asyncio
async def test_model_health_requires_admin_and_is_read_only():
    """A Lecturer must not reach the model-health endpoint, and the endpoint
    must expose no way to change which model is live.

    Promotion stays a deliberate CLI action behind compare_and_promote's gate —
    a web button would route around the safeguard this project added after a
    model went live ungated with no recoverable backup.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        admin = await _login(client)
        A = {"Authorization": f"Bearer {admin}"}

        r = await _create_user(client, admin, "mh_lect@probe.test", ["ICT104"])
        assert r.status_code == 201, r.text
        lect = (await client.post("/api/auth/login", json={
            "email": "mh_lect@probe.test", "password": "Probe@2025!"})).json()["access_token"]

        try:
            denied = await client.get("/api/admin/model-health",
                                      headers={"Authorization": f"Bearer {lect}"})
            assert denied.status_code == 403, (
                f"a Lecturer reached the model-health endpoint (got {denied.status_code})"
            )

            allowed = await client.get("/api/admin/model-health", headers=A)
            assert allowed.status_code == 200
            body = allowed.json()
            assert set(body) >= {"live_models", "accuracy", "fairness", "interventions"}
            assert "promotion_policy" in body["live_models"]
        finally:
            await client.delete("/api/users/mh_lect@probe.test", headers=A)

    # Read-only: no mutating route may exist under the model-health path.
    mutating = [
        (r.path, m) for r in app.routes
        if getattr(r, "path", "").startswith("/api/admin/model-health")
        for m in (getattr(r, "methods", set()) or set())
        if m in {"POST", "PUT", "PATCH", "DELETE"}
    ]
    assert not mutating, f"model-health exposes mutating routes: {mutating}"


@pytest.mark.asyncio
async def test_model_health_matches_a_fresh_direct_run_of_the_source_scripts():
    """The dashboard must report what the CLI scripts report — not a cached or
    separately-derived copy that can drift from them."""
    from app.ml.check_bias_persistence import collect as collect_bias
    from app.ml.model_registry import load_registry, get_live_entry
    from app.ml.sim_model_registry import load_registry as load_sim, get_live_entry as live_sim

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = await _login(client)
        body = (await client.get("/api/admin/model-health",
                                 headers={"Authorization": f"Bearer {token}"})).json()

    # Live model identity, straight from the registries right now.
    assert body["live_models"]["complete_record"]["version"] == get_live_entry(load_registry())["version"]
    assert body["live_models"]["mid_term"]["version"] == live_sim(load_sim())["version"]

    # Fairness: identical to a fresh direct call, including the dedupe rule
    # that stops a re-run on unchanged data counting as independent evidence.
    fresh_bias = collect_bias()
    assert body["fairness"]["independent_retrains"] == fresh_bias["independent_retrains"]
    assert body["fairness"]["enough_for_a_trend"] == fresh_bias["enough_for_a_trend"]
    assert (
        [(g["category"], g["group"], g["times_flagged"]) for g in body["fairness"]["flagged_groups"]]
        == [(g["category"], g["group"], g["times_flagged"]) for g in fresh_bias["flagged_groups"]]
    )

    # A single observation must never be presented as a trend.
    if body["fairness"]["independent_retrains"] < 2:
        assert body["fairness"]["enough_for_a_trend"] is False

    # Accuracy is measured on reconciled outcomes, and n must agree with the
    # per-group breakdown rather than being a separately-carried number.
    acc = body["accuracy"]
    if acc["overall"]:
        assert acc["overall"]["n"] == acc["reconciled_count"]
        by_type = [v["n"] for v in acc["by_estimate_type"].values() if v]
        assert sum(by_type) == acc["reconciled_count"]


def test_intervention_outcome_report_refuses_to_compare_on_thin_data():
    """The intervention/outcome comparison must decline to report a percentage
    when either group is too small, rather than printing a meaningless number.

    This is the current real state of the data (there are almost no logged
    interventions yet), and it is the behaviour that matters most: the failure
    mode for this comparison is overclaiming, not under-reporting.
    """
    from app.ml.intervention_outcome_report import render, MIN_GROUP_FOR_A_RATE

    thin = {
        "high_risk_reconciled": 29, "total_interventions_logged": 2,
        "with_intervention":    {"n": 1,  "pass_rate": 1.0},
        "without_intervention": {"n": 28, "pass_rate": 0.07},
        "sufficient_data": False, "min_group_for_a_rate": MIN_GROUP_FOR_A_RATE,
    }
    text = render(thin)
    assert "NOT ENOUGH DATA" in text
    assert "percentage points" not in text, (
        "a difference was reported despite one group having a single student"
    )

    ample = {
        "high_risk_reconciled": 400, "total_interventions_logged": 120,
        "with_intervention":    {"n": 100, "pass_rate": 0.60},
        "without_intervention": {"n": 300, "pass_rate": 0.40},
        "sufficient_data": True, "min_group_for_a_rate": MIN_GROUP_FOR_A_RATE,
    }
    rich = render(ample)
    assert "+20.0 percentage points" in rich
    # ...but never as proof.
    assert "NOT EVIDENCE THAT INTERVENTIONS WORK" in rich

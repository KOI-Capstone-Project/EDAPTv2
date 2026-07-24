"""EDAPT v2 — ML inference wrapper. Loads the live model version once at import time."""

from pathlib import Path
from typing import Optional

import joblib
import numpy as np

from app.ml.train_model import FAIL_THRESHOLD
from app.ml.model_registry import load_live_model, load_registry, get_live_entry
from app.ml.explain import explain_prediction, MAIN_BACKGROUND, SIM_BACKGROUND

# ── Load model packages at startup ────────────────────────────────────────────
# _PACKAGE now comes from the version registry (model_registry.py), not a
# hardcoded best_model.pkl path — see compare_and_promote.py for how a new
# trained version becomes live. First run with no registry yet transparently
# migrates the existing best_model.pkl in as version 1, live from the start,
# so this is a zero-disruption change to whatever's already deployed.

_PACKAGE: Optional[dict] = load_live_model()
if _PACKAGE is None:
    print("WARNING: No live ML model version found. Run train_model.py, "
          "then compare_and_promote.py --promote to activate a version.")

# The registry version id actually serving predict() right now — persisted
# alongside every logged prediction (see main.py) so a later accuracy report
# can be broken down by which model version was live when each prediction
# was made, not just lumped together.
_live_entry = get_live_entry(load_registry())
LIVE_MODEL_VERSION: Optional[str] = _live_entry["version"] if _live_entry else None

# Second model, trained on simulated mid-term partial-progress snapshots
# (train_simulated_progress.py) — used only for genuinely partial records
# (50-99% coverage). Optional: if missing, classify_coverage's "partial" tier
# simply becomes unservable (predict_partial returns an error dict) rather
# than the app failing to start.
_SIM_PKG_PATH = Path(__file__).parent / "best_model_simulated_progress.pkl"

if _SIM_PKG_PATH.exists():
    _SIM_PACKAGE: Optional[dict] = joblib.load(_SIM_PKG_PATH)
else:
    _SIM_PACKAGE = None
    print(f"WARNING: simulated-progress ML model not found at {_SIM_PKG_PATH}. "
          f"Run train_simulated_progress.py to enable mid-term estimates.")

# This model isn't in the version registry (it's a separate, not-yet-deployed
# family — see its own "deployed": False flag) so it has no registry version
# id. Use its trained_at timestamp instead — still a stable, traceable
# identifier back to a specific saved model package, just not a registry entry.
SIM_MODEL_VERSION: Optional[str] = (
    f"simulated_progress_{_SIM_PACKAGE['trained_at']}" if _SIM_PACKAGE else None
)

# ── Coverage-based routing ───────────────────────────────────────────────────
# >= COMPLETE_COVERAGE_THRESHOLD : best_model.pkl (today's behaviour, unchanged)
# MIN_COVERAGE_FOR_PREDICTION .. COMPLETE_COVERAGE_THRESHOLD : best_model_simulated_progress.pkl
# < MIN_COVERAGE_FOR_PREDICTION : no prediction — "insufficient data yet"
#
# COMPLETE_COVERAGE_THRESHOLD is 99.5, not a strict ==100, purely as floating-
# point tolerance on a weighting sum — this is not a policy change from "100%
# recorded", real assessment weightings just don't always sum to exactly
# 100.0 in float64.
COMPLETE_COVERAGE_THRESHOLD = 99.5
MIN_COVERAGE_FOR_PREDICTION = 50.0


def classify_coverage(cumulative_weighting_recorded: float) -> str:
    """Return 'complete' / 'partial' / 'insufficient' for a coverage percentage (0-100)."""
    if cumulative_weighting_recorded >= COMPLETE_COVERAGE_THRESHOLD:
        return "complete"
    if cumulative_weighting_recorded >= MIN_COVERAGE_FOR_PREDICTION:
        return "partial"
    return "insufficient"

# ── Feature recomputation ───────────────────────────────────────────────────

def compute_partial_score(assessments_used: list) -> tuple:
    """
    Derive (partial_weighted_score, partial_weight_coverage) from raw recorded
    assessment items, using the exact same top-2-by-weight logic as
    train_model.py's build_early_features(): sort by weighting descending,
    take the top 2, sum their mark*weight/100 contributions.

    Callers must NOT trust a client-supplied partial_weighted_score/coverage —
    a client summing ALL recorded items (not just the top 2) would silently
    feed the model a feature value outside the distribution it was trained on,
    since the ensemble has only ever seen the top-2-capped version of this
    feature (see build_early_features()'s docstring for why "all items" isn't
    safe on this dataset). Always recompute from assessments_used instead.

    assessments_used: list of {"mark_percent": float, "weighting": float, ...}
    """
    if not assessments_used:
        return 0.0, 0.0
    sorted_items = sorted(assessments_used, key=lambda a: a["weighting"], reverse=True)

    a1 = sorted_items[0]
    a1_contrib = a1["mark_percent"] * a1["weighting"] / 100

    if len(sorted_items) > 1:
        a2 = sorted_items[1]
        a2_contrib = a2["mark_percent"] * a2["weighting"] / 100
        a2_weight  = a2["weighting"]
    else:
        a2_contrib = 0.0
        a2_weight  = 0.0

    partial_weighted_score  = a1_contrib + a2_contrib
    partial_weight_coverage = (a1["weighting"] + a2_weight) / 100
    return partial_weighted_score, partial_weight_coverage


def compute_simulated_partial_score(assessments_used: list) -> tuple:
    """
    Derive (partial_weighted_score, partial_weight_coverage) as a cumulative
    sum across ALL items in assessments_used — not just the top 2. This
    mirrors train_model.py's build_simulated_progress_features() exactly,
    which is what best_model_simulated_progress.pkl was trained on. Only
    valid for genuinely partial records (assessments_used representing less
    than a complete term) — see build_early_features()'s docstring for why
    this same "sum everything" formula is a leakage risk for complete
    records, which is precisely why complete records never reach this
    function (classify_coverage routes them to predict()/compute_partial_score
    instead).

    assessments_used: list of {"mark_percent": float, "weighting": float, ...}
    """
    if not assessments_used:
        return 0.0, 0.0
    total_score  = sum(a["mark_percent"] * a["weighting"] / 100 for a in assessments_used)
    total_weight = sum(a["weighting"] for a in assessments_used)
    return float(total_score), float(total_weight) / 100


def _top2_by_weight(assessments_used: list):
    """Return (a1_mark, a1_weight, a1_contribution, a2_mark, a2_weight, a2_contribution)
    for the two highest-weighted items in assessments_used (0.0s if fewer than 2)."""
    if not assessments_used:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
    sorted_items = sorted(assessments_used, key=lambda a: a["weighting"], reverse=True)
    a1 = sorted_items[0]
    a1_mark, a1_weight = float(a1["mark_percent"]), float(a1["weighting"])
    a1_contrib = a1_mark * a1_weight / 100
    if len(sorted_items) > 1:
        a2 = sorted_items[1]
        a2_mark, a2_weight = float(a2["mark_percent"]), float(a2["weighting"])
    else:
        a2_mark, a2_weight = 0.0, 0.0
    a2_contrib = a2_mark * a2_weight / 100
    return a1_mark, a1_weight, a1_contrib, a2_mark, a2_weight, a2_contrib


def _compute_risk_band(probability: float, threshold: float) -> str:
    """
    Safe / At Risk / High Risk banding, derived from whichever decision
    threshold actually produced the Pass/Fail label for this prediction —
    not a hardcoded 65/40 split shared blindly across models.

    Bug this fixes: predict() and predict_partial() use DIFFERENT decision
    thresholds (0.50 vs 0.25, both honestly validated via validate_threshold.py
    against their own held-out split) but previously shared one hardcoded
    65/40 risk-band split. Whenever a threshold's implied Fail/Pass boundary
    (100 * (1 - threshold)) sits ABOVE the band's Safe floor, a probability
    can be "Fail" by the label and "Safe" by the band simultaneously —
    confirmed live: ICT101/25.1, ME 45/50 (mid-term estimate, threshold=0.25)
    produced probability=73.1, prediction="Fail", risk_band="Safe".

    Fix: the Safe floor is never allowed to sit below the threshold's own
    Fail/Pass boundary, so "Safe" and "Fail" can never co-occur — proven by
    construction, not just for today's specific threshold values. This is a
    genuine behavior change for predict_partial() (Safe floor raised from
    65 to 75, since its threshold is 0.25, not 0.50) but NOT for predict()
    (FAIL_THRESHOLD=0.50 already sits below 65, so its Safe floor stays 65,
    unchanged — verified via test_smoke.py).

    The 0.25 mid-term threshold itself is intentionally NOT changed to 0.50
    here — it was honestly validated (same validate_threshold.py-style
    methodology as FAIL_THRESHOLD) to land in the 80-85% recall band for
    partial-coverage predictions specifically; forcibly using 0.50 instead
    would silently discard that validation and measurably reduce mid-term
    fail-detection recall. See model_card.md's Issue 5 writeup for the
    quantified tradeoff and the alternative (uniform 0.50 + fixed bands)
    this was weighed against.
    """
    # prediction is "Fail" when proba_fail >= threshold, i.e. when
    # probability <= 100*(1-threshold) — so "Safe" must require probability
    # STRICTLY greater than that cutoff, not >=, or the exact boundary value
    # would satisfy both "Fail" (>=) and "Safe" (>=) simultaneously. Caught
    # by test_compute_risk_band_never_contradicts_threshold at probability=75,
    # threshold=0.25 before this shipped.
    fail_cutoff = 100 * (1 - threshold)
    if probability > fail_cutoff and probability >= 65:
        return "Safe"
    elif probability >= 40:
        return "At Risk"
    else:
        return "High Risk"


# ── Inference ─────────────────────────────────────────────────────────────────

def predict(
    subject:                 str,
    study_period:            str,
    trimester_num:           float,
    assess1_mark:            float,
    assess1_weight:          float,
    assess1_contribution:    float,
    assess2_mark:            float,
    assess2_weight:          float,
    assess2_contribution:    float,
    partial_weighted_score:  float,
    partial_weight_coverage: float,
    num_assessments:         int,
    total_weight_recorded:   float,
    weight_complete:         bool,
    assessments_used:        list,
) -> dict:
    """Return a prediction dict or an error dict if the model is not loaded."""
    if _PACKAGE is None:
        return {"error": "model_not_loaded"}

    model           = _PACKAGE["model"]
    subj_difficulty = _PACKAGE["subject_difficulty"].get(subject, 0.2)

    # FEATURES order must match train_model.py FEATURES list exactly
    feature_values = np.array([[
        assess1_mark, assess1_weight, assess1_contribution,
        assess2_mark, assess2_weight, assess2_contribution,
        partial_weighted_score, partial_weight_coverage,
        subj_difficulty, trimester_num,
    ]])

    # model.classes_ == [0, 1] where 0=Fail, 1=Pass (train_model.py's PASS target
    # encoding) — column 1 is P(Pass), column 0 is P(Fail). Verified directly
    # against the saved model, not assumed, since a swapped index here would
    # silently invert every prediction.
    proba_arr   = model.predict_proba(feature_values)[0]
    proba_pass  = float(proba_arr[1])
    proba_fail  = float(proba_arr[0])
    probability = round(proba_pass * 100, 1)

    # FAIL_THRESHOLD (0.50, from train_model.py) is the validation-selected value —
    # see validate_threshold.py. Gives recall 0.837 / precision 0.770 on the T3
    # 2025 test set. The displayed probability is untouched, since it already
    # operates on the continuous P(Pass) score, not this binary cutoff — but
    # risk_band is derived from this SAME threshold (_compute_risk_band), so
    # "Safe" and "Fail" can never contradict each other. See that function's
    # docstring for why this used to be able to happen.
    prediction = "Fail" if proba_fail >= FAIL_THRESHOLD else "Pass"
    risk_band  = _compute_risk_band(probability, FAIL_THRESHOLD)

    # Computed from feature_values — the exact row just scored above — and
    # _PACKAGE — the exact model object that scored it, never re-derived or
    # re-loaded. See explain.py for why this is safe against a stale model.
    shap_explanation = explain_prediction(_PACKAGE, MAIN_BACKGROUND, feature_values)

    return {
        "subject":                subject,
        "study_period":           study_period,
        "probability":            probability,
        "prediction":             prediction,
        "risk_band":              risk_band,
        "subject_difficulty":     subj_difficulty,
        "num_assessments_used":   num_assessments,
        "total_weight_recorded":  total_weight_recorded,
        "weight_complete":        weight_complete,
        "partial_weighted_score": partial_weighted_score,
        "model_name":             _PACKAGE["model_name"],
        "model_accuracy":         _PACKAGE["accuracy"],
        "model_version":          LIVE_MODEL_VERSION,
        "gemini_insight":         None,
        "shap_explanation":       shap_explanation,
        "assessments_used":       assessments_used,
    }


def predict_partial(
    subject:          str,
    study_period:     str,
    trimester_num:    float,
    assessments_used: list,
) -> dict:
    """
    Mid-term estimate for a genuinely partial record (50-99% coverage) —
    routed here by classify_coverage(), never called directly for complete
    records. Uses best_model_simulated_progress.pkl, and computes
    PARTIAL_WEIGHTED_SCORE/COVERAGE as a cumulative sum across ALL of
    assessments_used (compute_simulated_partial_score), not the top-2-only
    formula predict() uses — this model was trained on that definition
    (train_simulated_progress.py), so using the other one here would silently
    feed it an out-of-distribution feature, the same class of bug the
    top-2-vs-sum-of-all mismatch was for the complete-record model.

    This is a self-contained function, not a variant of predict(), so predict()
    itself never has to change — the complete-record path (best_model.pkl) is
    guaranteed untouched by anything in here.
    """
    if _SIM_PACKAGE is None:
        return {"error": "simulated_progress_model_not_loaded"}

    model           = _SIM_PACKAGE["model"]
    subj_difficulty = _SIM_PACKAGE["subject_difficulty"].get(subject, 0.2)
    threshold       = _SIM_PACKAGE["decision_threshold"]

    a1_mark, a1_weight, a1_contrib, a2_mark, a2_weight, a2_contrib = _top2_by_weight(assessments_used)
    partial_weighted_score, partial_weight_coverage = compute_simulated_partial_score(assessments_used)

    # FEATURES order must match train_model.py FEATURES list exactly (same order
    # as predict() — build_simulated_progress_features() produces the same
    # column set, just different values for the partial-score/coverage pair).
    feature_values = np.array([[
        a1_mark, a1_weight, a1_contrib,
        a2_mark, a2_weight, a2_contrib,
        partial_weighted_score, partial_weight_coverage,
        subj_difficulty, trimester_num,
    ]])

    proba_arr   = model.predict_proba(feature_values)[0]
    proba_pass  = float(proba_arr[1])
    proba_fail  = float(proba_arr[0])
    probability = round(proba_pass * 100, 1)

    prediction = "Fail" if proba_fail >= threshold else "Pass"

    # risk_band is derived from THIS model's own threshold (0.25, not
    # predict()'s 0.50) via _compute_risk_band — previously hardcoded to the
    # same 65/40 split as predict() regardless of threshold, which could show
    # "Safe" and "Fail" simultaneously (confirmed live: probability=73.1,
    # threshold=0.25 → Fail, but 73.1 >= the old hardcoded 65 → Safe). The
    # simulated-progress model's probabilities also run less confident on
    # average (verified: precision 0.23-0.57 across coverage bins vs. 0.77
    # for a complete record), which is exactly why "mid-term estimate" is
    # called out explicitly rather than presented identically to a
    # complete-record prediction.
    risk_band = _compute_risk_band(probability, threshold)

    # Separate cache entry keyed off _SIM_PACKAGE["model"] (a distinct object
    # from the complete-record ensemble) and the sim-specific background
    # sample — never mixed with the complete-record explainer/background.
    shap_explanation = explain_prediction(_SIM_PACKAGE, SIM_BACKGROUND, feature_values)

    return {
        "subject":                subject,
        "study_period":           study_period,
        "probability":            probability,
        "prediction":             prediction,
        "risk_band":              risk_band,
        "subject_difficulty":     subj_difficulty,
        "num_assessments_used":   len(assessments_used),
        "total_weight_recorded":  partial_weight_coverage * 100,
        "weight_complete":        False,
        "partial_weighted_score": partial_weighted_score,
        "model_name":             _SIM_PACKAGE["model_name"],
        "model_accuracy":         _SIM_PACKAGE["accuracy"],
        "model_version":          SIM_MODEL_VERSION,
        "gemini_insight":         None,
        "shap_explanation":       shap_explanation,
        "assessments_used":       assessments_used,
        "estimate_type":          "mid-term estimate",
    }

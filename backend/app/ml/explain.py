"""
EDAPT v2 — Real SHAP feature attributions for a single prediction.

The deployed model is a soft-voting sklearn VotingClassifier over an
XGBoost classifier and a RandomForestClassifier (train_model.py Step 4).
SHAP has no explainer that understands VotingClassifier directly, and a
model-agnostic explainer (KernelExplainer) would be needlessly slow and
approximate for two tree models we can explain exactly. So this explains
each sub-model separately with shap.TreeExplainer and combines the two:

  - Both sub-models are explained with feature_perturbation="interventional"
    and model_output="probability" (not the default "raw"/log-odds margin),
    using a small cached background sample (build_shap_background.py) — this
    is what makes the SHAP values land directly in probability space, so
    they sum with a base value to reconstruct the model's actual P(Pass).
  - VotingClassifier(voting="soft") with no explicit `weights` computes
    predict_proba as a plain, equal-weight average of its sub-estimators'
    predict_proba. SHAP values are linear in the value function being
    explained, so the equal-weight average of each sub-model's SHAP values
    is exactly the SHAP explanation of that equal-weight average model —
    this was verified empirically (not just assumed): averaging the two
    sub-explainers' outputs reconstructs the live ensemble's actual
    predict_proba to ~1e-8, for real feature rows from this project's data.

sklearn's RandomForestClassifier explainer returns SHAP values per class
(shape (n_samples, n_features, n_classes)); XGBClassifier's binary
"probability"-mode explainer returns a single (n_samples, n_features) array
already in terms of the positive class. Both are normalised here to "SHAP
value for P(Pass), class index 1" before averaging, so the two sub-model
explanations are directly comparable.

Usage: explain_prediction(model_package, background, feature_values) is
called from predictor.py right after computing a prediction — never called
standalone with an arbitrary/stale model, always the exact same model_package
object (and therefore exact same fitted sub-estimators) that produced the
prediction being explained.
"""

from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import shap

_BG_DIR = Path(__file__).resolve().parent
MAIN_BACKGROUND_PATH = _BG_DIR / "shap_background_main.pkl"
SIM_BACKGROUND_PATH  = _BG_DIR / "shap_background_simulated.pkl"

# A mismatch here would mean the explanation doesn't actually add up to the
# number it's explaining — worth surfacing loudly (see explain_prediction's
# "sum_check_ok"), not silently swallowing a real discrepancy.
SUM_CHECK_TOLERANCE = 0.01

# explainer cache, keyed by id(fitted ensemble model) — a package is loaded
# once at startup and reused for the process lifetime, so this never rebuilds
# an explainer for the same live model twice, but also never reuses one across
# a version change (a freshly loaded model_package is a new object with a new
# id, so a stale explainer for a retired version is never served).
_explainer_cache: dict = {}


def _load_background(path: Path) -> Optional[np.ndarray]:
    if not path.exists():
        print(f"WARNING: SHAP background not found at {path} — "
              f"run `python -m app.ml.build_shap_background` to enable explanations. "
              f"Predictions will still work; shap_explanation will be omitted.")
        return None
    return joblib.load(path)


MAIN_BACKGROUND = _load_background(MAIN_BACKGROUND_PATH)
SIM_BACKGROUND  = _load_background(SIM_BACKGROUND_PATH)


def _build_explainers(model, background: np.ndarray):
    xgb_model = model.named_estimators_["xgb"]
    rf_model  = model.named_estimators_["rf"]
    exp_xgb = shap.TreeExplainer(
        xgb_model, data=background, model_output="probability", feature_perturbation="interventional",
    )
    exp_rf = shap.TreeExplainer(
        rf_model, data=background, model_output="probability", feature_perturbation="interventional",
    )
    return exp_xgb, exp_rf


def _get_explainers(model, background: np.ndarray):
    key = id(model)
    if key not in _explainer_cache:
        _explainer_cache[key] = _build_explainers(model, background)
    return _explainer_cache[key]


def explain_prediction(model_package: dict, background: Optional[np.ndarray], feature_values: np.ndarray) -> Optional[dict]:
    """
    feature_values: shape (1, n_features), same array already built and
    passed to model.predict_proba() by the caller (predictor.py) — this
    function never recomputes or re-derives features itself, so the
    explanation is guaranteed to be about the exact row that was scored.

    Returns None if no background is cached (SHAP explanation is an add-on;
    its absence must never block a prediction from being returned).
    """
    if background is None:
        return None

    model = model_package["model"]
    feature_names = model_package["features"]

    exp_xgb, exp_rf = _get_explainers(model, background)

    sv_xgb = np.array(exp_xgb.shap_values(feature_values))          # (1, n_features) — already P(class 1)
    sv_rf_full = np.array(exp_rf.shap_values(feature_values))       # (1, n_features, n_classes)
    sv_rf = sv_rf_full[..., 1]                                      # class-1 (Pass) slice -> (1, n_features)

    # exp_xgb.expected_value is a scalar (binary "probability"-mode output is
    # already single-valued, P(class 1)); np.ravel(...)[-1] normalises that
    # and the single-element-array case identically. exp_rf.expected_value is
    # a 2-element [P(class 0), P(class 1)] array — index 1 for Pass.
    base_xgb = float(np.ravel(exp_xgb.expected_value)[-1])
    base_rf  = float(np.ravel(exp_rf.expected_value)[1])

    ens_shap = ((sv_xgb + sv_rf) / 2)[0]        # (n_features,) — equal-weight average, matches soft voting
    ens_base = (base_xgb + base_rf) / 2

    predicted_pass_probability = float(model.predict_proba(feature_values)[0][1])
    reconstructed = float(ens_base + ens_shap.sum())
    delta = abs(reconstructed - predicted_pass_probability)

    factors = []
    # strict=True deliberately: a length mismatch between the model's feature
    # names, the submitted values and the SHAP row is exactly the failure this
    # project already hit once (a 10-column SHAP background cached against an
    # 11-feature model). Fail loudly rather than silently truncate.
    for name, value, shap_val in zip(feature_names, feature_values[0], ens_shap, strict=True):
        factors.append({
            "feature":       name,
            "value":         float(value),
            "contribution":  round(float(shap_val) * 100, 2),   # percentage points of P(Pass), same 0-100 scale as `probability`
            "direction":     "Pass" if shap_val > 0 else ("Fail" if shap_val < 0 else "Neutral"),
        })
    factors.sort(key=lambda f: abs(f["contribution"]), reverse=True)

    return {
        "method":                      "SHAP TreeExplainer (XGBoost + RandomForest sub-models, averaged per soft-voting weights)",
        "base_value":                  round(ens_base * 100, 2),
        "predicted_pass_probability":  round(predicted_pass_probability * 100, 2),
        "reconstructed_probability":   round(reconstructed * 100, 2),
        "sum_check_delta":             round(delta * 100, 4),
        "sum_check_ok":                delta < SUM_CHECK_TOLERANCE,
        "top_factors":                 factors[:3],
        "all_factors":                 factors,
    }

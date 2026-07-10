"""EDAPT v2 — ML inference wrapper. Loads best_model.pkl once at import time."""

from pathlib import Path
from typing import Optional

import joblib
import numpy as np

# ── Load model package at startup ─────────────────────────────────────────────

_PKG_PATH = Path(__file__).parent / "best_model.pkl"

if _PKG_PATH.exists():
    _PACKAGE: Optional[dict] = joblib.load(_PKG_PATH)
else:
    _PACKAGE = None
    print(f"WARNING: ML model not found at {_PKG_PATH}. Run train_model.py first.")

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

    proba       = float(model.predict_proba(feature_values)[0][1])
    probability = round(proba * 100, 1)

    prediction = "Pass" if probability >= 50 else "Fail"

    if probability >= 65:
        risk_band = "Safe"
    elif probability >= 40:
        risk_band = "At Risk"
    else:
        risk_band = "High Risk"

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
        "gemini_insight":         None,
        "assessments_used":       assessments_used,
    }

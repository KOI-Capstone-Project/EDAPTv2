"""
EDAPT v2 — Build cached background samples for SHAP explanations.

shap.TreeExplainer's interventional feature_perturbation (the mode that lets
it explain probability output directly, not raw log-odds margin — see
explain.py) needs a background dataset representing the feature
distribution the model was trained on. Computing that background live
(via train_model.prepare_data()) costs ~7s for the complete-record model
and ~55s for the simulated-progress model (train_simulated_progress.py's
multi-snapshot feature generation is much more expensive) — both far too
slow to redo on every backend startup, let alone per request.

This script computes a small (100-row) random sample of each model's
actual training feature matrix ONCE and caches it to disk. explain.py just
loads these small arrays at import time — near-instant.

Re-run this after any retrain that meaningfully shifts the underlying
feature distribution (e.g. a new study period rolling in changes
SUBJECT_DIFFICULTY's realistic range). Not required after every retrain —
this is a baseline reference for SHAP's expected-value calculation, not
part of the model itself, so a slightly stale background is a minor
accuracy tradeoff on the explanation, not a correctness bug in the
prediction.

Usage (run from backend/, as a module):
    python -m app.ml.build_shap_background
"""

from pathlib import Path

import joblib
import numpy as np

from app.ml.train_model import prepare_data
from app.ml.train_simulated_progress import build_simulated_progress_features

OUT_DIR = Path(__file__).resolve().parent
MAIN_BACKGROUND_PATH = OUT_DIR / "shap_background_main.pkl"
SIM_BACKGROUND_PATH  = OUT_DIR / "shap_background_simulated.pkl"

BACKGROUND_SIZE = 100
RANDOM_STATE = 42


def _sample(X: np.ndarray) -> np.ndarray:
    rng = np.random.RandomState(RANDOM_STATE)
    n = min(BACKGROUND_SIZE, X.shape[0])
    idx = rng.choice(X.shape[0], size=n, replace=False)
    return X[idx]


def main() -> None:
    print("═" * 70)
    print("Building SHAP background — complete-record model (build_early_features)")
    print("═" * 70)
    X_train, *_ = prepare_data()
    main_bg = _sample(X_train)
    joblib.dump(main_bg, MAIN_BACKGROUND_PATH)
    print(f"  ✓ Saved {main_bg.shape[0]} background rows -> {MAIN_BACKGROUND_PATH.name}")

    print("\n" + "═" * 70)
    print("Building SHAP background — simulated-progress model (build_simulated_progress_features)")
    print("═" * 70)
    X_train_sim, *_ = prepare_data(feature_builder=build_simulated_progress_features)
    sim_bg = _sample(X_train_sim)
    joblib.dump(sim_bg, SIM_BACKGROUND_PATH)
    print(f"  ✓ Saved {sim_bg.shape[0]} background rows -> {SIM_BACKGROUND_PATH.name}")


if __name__ == "__main__":
    main()

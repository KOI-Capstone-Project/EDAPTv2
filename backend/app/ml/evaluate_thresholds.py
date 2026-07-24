"""
EDAPT v2 — Threshold analysis for the Fail class.

The default classification threshold (predict Fail if P(fail) >= 0.5) is not
necessarily the right operating point for an at-risk detection system, where
missing a genuinely failing student (a false negative) is usually worse than
an unnecessary check-in on a student who was actually fine (a false positive).
This script reuses the exact data pipeline and the LIVE saved model (via
model_registry, not a hardcoded best_model.pkl path — that file stops being
current the moment any retrain happens under the versioning system) from
train_model.py — it does not retrain anything — and sweeps the decision
threshold to show the precision/recall tradeoff at each point, so the
operating threshold can be chosen deliberately instead of defaulting to 0.5.

Usage (run from backend/, as a module):
    python -m app.ml.evaluate_thresholds
"""

import numpy as np
from sklearn.metrics import precision_score, recall_score, f1_score

from app.ml.train_model import prepare_data
from app.ml.model_registry import load_live_model

THRESHOLDS = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]


def main() -> None:
    print("Loading the live model from the registry …")
    model_package = load_live_model()
    if model_package is None:
        raise RuntimeError("No live model in the registry — run train_model.py and promote a version first.")
    ensemble = model_package["model"]

    print("Reproducing the test set via train_model.prepare_data() (no retraining) …")
    _, _, X_test, y_test, _, _, _ = prepare_data()
    print(f"Test set: {len(y_test):,} rows  ({int((y_test==0).sum()):,} fail / {int((y_test==1).sum()):,} pass)")

    # ensemble.classes_ is [0, 1] = [Fail, Pass]; column 0 is P(fail).
    proba_fail = ensemble.predict_proba(X_test)[:, 0]

    print("\n── Precision / Recall / F1 for the FAIL class at each threshold ──────")
    print(f"{'Threshold':>10}  {'Precision':>10}  {'Recall':>8}  {'F1':>6}  {'Flagged as Fail':>16}")
    print("-" * 62)
    results = []
    for t in THRESHOLDS:
        pred_fail = (proba_fail >= t).astype(int)   # 1 = predicted Fail
        true_fail = (y_test == 0).astype(int)
        precision = precision_score(true_fail, pred_fail, zero_division=0)
        recall    = recall_score(true_fail, pred_fail, zero_division=0)
        f1        = f1_score(true_fail, pred_fail, zero_division=0)
        n_flagged = int(pred_fail.sum())
        results.append((t, precision, recall, f1, n_flagged))
        print(f"{t:>10.2f}  {precision:>10.3f}  {recall:>8.3f}  {f1:>6.3f}  {n_flagged:>16,}")

    print("\n── Thresholds landing in the 0.80-0.85 recall band ───────────────────")
    band = [r for r in results if 0.80 <= r[2] <= 0.85]
    if band:
        best = max(band, key=lambda r: r[1])  # highest precision within the band
        for t, p, r, f1, n in band:
            marker = "  ← best precision in band" if (t, p, r, f1, n) == best else ""
            print(f"  threshold={t:.2f}  precision={p:.3f}  recall={r:.3f}  f1={f1:.3f}{marker}")
    else:
        print("  No swept threshold landed exactly in 0.80-0.85 — see full table above.")


if __name__ == "__main__":
    main()

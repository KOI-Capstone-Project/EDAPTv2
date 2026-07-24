"""
EDAPT v2 — Multi-snapshot simulated-progress training experiment.

Extends the roster endpoint's simulate_progress truncation logic into
TRAINING data generation (build_simulated_progress_features() in
train_model.py), instead of the fixed top-2-highest-weighted-assessment cap.
For each real, fully-graded enrolment, generates up to 4 synthetic
partial-progress rows (one stratified draw from each of 15-30%, 30-50%,
50-70%, 70-90% cumulative-weighting cutoff, sorted by submission order —
STUDYPACKAGEASSESSMENTID — not by weight).

Follows the same validation-then-test methodology as validate_threshold.py:
  1. Fit a model on TRAIN ONLY (<25.2).
  2. Sweep thresholds on VALIDATION (25.2), pick the one landing in the
     0.80-0.85 recall band.
  3. Fit a deployed-equivalent model on train+validation (<25.3, matching how
     best_model.pkl is actually trained) and report on the untouched TEST
     set (25.3) at the validation-selected threshold — overall, and broken
     out by actual achieved coverage bin.

Does NOT overwrite backend/app/ml/best_model.pkl — see the "NOT DEPLOYED"
section printed at the end for why.

Usage (run from backend/, as a module — its imports are package-qualified
so a bare `python backend/app/ml/train_simulated_progress.py` no longer
resolves them):
    python -m app.ml.train_simulated_progress
"""

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from imblearn.over_sampling import SMOTE
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.metrics import precision_score, recall_score, f1_score, classification_report
from xgboost import XGBClassifier

from app.ml.train_model import (
    prepare_data_3way, prepare_data, build_simulated_progress_features, FEATURES,
)

MODEL_OUT  = Path(__file__).resolve().parent / "best_model_simulated_progress.pkl"
# Wider and finer than the full-record sweep (0.30-0.70) — simulated-progress
# probabilities are pulled toward the base rate at low coverage, so the
# optimum can sit well below 0.30. Extend down to 0.05 rather than assume the
# earlier range still applies.
THRESHOLDS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]
BIN_EDGES  = [(15, 30), (30, 50), (50, 70), (70, 90)]


def fail_metrics(y_true_pass, proba_fail, threshold):
    pred_fail = (proba_fail >= threshold).astype(int)
    true_fail = (y_true_pass == 0).astype(int)
    return (
        precision_score(true_fail, pred_fail, zero_division=0),
        recall_score(true_fail, pred_fail, zero_division=0),
        f1_score(true_fail, pred_fail, zero_division=0),
        int(pred_fail.sum()),
    )


def fit_ensemble(X_train, y_train):
    smote = SMOTE(random_state=42)
    X_res, y_res = smote.fit_resample(X_train, y_train)
    xgb = XGBClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        random_state=42, eval_metric="logloss", verbosity=0,
    )
    rf = RandomForestClassifier(
        n_estimators=200, max_depth=6, class_weight="balanced",
        random_state=42, n_jobs=-1,
    )
    ensemble = VotingClassifier(estimators=[("xgb", xgb), ("rf", rf)], voting="soft")
    ensemble.fit(X_res, y_res)
    return ensemble


def leakage_check(data: pd.DataFrame) -> None:
    print("\n" + "=" * 70)
    print("LEAKAGE CHECK — does PARTIAL_WEIGHTED_SCORE reconstruct PASS?")
    print("=" * 70)
    print("(This is the same check that caught the sum-of-all-items leakage")
    print(" last time: agreement between (PARTIAL_WEIGHTED_SCORE >= 50) and")
    print(" the true PASS label. Near 100% agreement = leaking. Meaningfully")
    print(" below 100%, and rising with coverage, = genuine partial signal.)\n")

    agree_all = ((data["PARTIAL_WEIGHTED_SCORE"] >= 50).astype(int) == data["PASS"]).mean()
    print(f"Overall agreement (all {len(data):,} simulated rows): {agree_all*100:.1f}%")

    print(f"\n{'BIN':<12} {'N':>8} {'AGREEMENT':>10}")
    print("-" * 34)
    for lo, hi in BIN_EDGES:
        mask = data["SIM_ACHIEVED_COVERAGE"].between(lo, hi, inclusive="right")
        sub = data[mask]
        if sub.empty:
            continue
        agree = ((sub["PARTIAL_WEIGHTED_SCORE"] >= 50).astype(int) == sub["PASS"]).mean()
        print(f"{lo}-{hi}%{'':<7} {len(sub):>8,} {agree*100:>9.1f}%")

    if agree_all > 0.97:
        print("\n  ✗ STOP — agreement is suspiciously high, this looks like leakage.")
        raise SystemExit(1)
    print("\n  ✓ No leakage detected — agreement is well below 100% and scales with coverage, as expected.")


def main() -> None:
    # ── Step A: build the full simulated dataset once, for the leakage check ──
    print("═" * 70)
    print("Building simulated-progress features on the full filtered dataset (leakage check only)")
    print("═" * 70)
    from app.ml.train_model import load_and_filter_raw, build_target
    raw, _ = load_and_filter_raw()
    feat = build_simulated_progress_features(raw)
    target = build_target(raw)
    full_data = feat.merge(target, on=["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"], how="inner")
    leakage_check(full_data)

    # ── Step B: fit a TRAIN-ONLY model (<25.2) for honest threshold selection ──
    print("\n" + "═" * 70)
    print("STEP B — Train-only model (<25.2) on simulated-progress features")
    print("═" * 70)
    X_train, y_train, X_val, y_val, _, _, val_df, _, _, _ = prepare_data_3way(
        feature_builder=build_simulated_progress_features
    )
    val_model = fit_ensemble(X_train, y_train)
    print("Train-only model fitted.")

    proba_fail_val = val_model.predict_proba(X_val)[:, 0]
    print(f"\nValidation set: {len(y_val):,} simulated rows ({int((y_val==0).sum()):,} fail / {int((y_val==1).sum()):,} pass)")
    print(f"\n{'Threshold':>10}  {'Precision':>10}  {'Recall':>8}  {'F1':>6}")
    print("-" * 42)
    val_results = []
    for t in THRESHOLDS:
        p, r, f1, _ = fail_metrics(y_val, proba_fail_val, t)
        val_results.append((t, p, r, f1))
        print(f"{t:>10.2f}  {p:>10.3f}  {r:>8.3f}  {f1:>6.3f}")

    band = [row for row in val_results if 0.80 <= row[2] <= 0.85]
    chosen = max(band, key=lambda row: row[1]) if band else min(
        val_results, key=lambda row: min(abs(row[2] - 0.80), abs(row[2] - 0.85))
    )
    chosen_threshold = chosen[0]
    print(f"\nSelected on validation: threshold={chosen_threshold:.2f} "
          f"(precision={chosen[1]:.3f}, recall={chosen[2]:.3f}, f1={chosen[3]:.3f})")

    # ── Step C: fit the deployed-EQUIVALENT model (train+val, <25.3) ──────────
    print("\n" + "═" * 70)
    print("STEP C — Deployed-equivalent model (<25.3) on simulated-progress features")
    print("═" * 70)
    X_train_full, y_train_full, X_test, y_test, test_df, subject_difficulty, safe_subjects = prepare_data(
        feature_builder=build_simulated_progress_features
    )
    deployed = fit_ensemble(X_train_full, y_train_full)
    print("Deployed-equivalent model fitted.")

    proba_fail_test = deployed.predict_proba(X_test)[:, 0]
    p, r, f1, n = fail_metrics(y_test, proba_fail_test, chosen_threshold)
    print(f"\nOverall TEST (25.3) performance at threshold {chosen_threshold:.2f}, {len(y_test):,} simulated rows:")
    print(f"  Fail — precision={p:.3f}  recall={r:.3f}  f1={f1:.3f}  (flagged as Fail: {n:,})")

    # ── Step D: breakdown by ACHIEVED coverage bin ─────────────────────────────
    print("\n" + "═" * 70)
    print("STEP D — Performance by progress-cutoff range (actual achieved coverage)")
    print("═" * 70)
    test_df = test_df.reset_index(drop=True)
    proba_fail_series = pd.Series(proba_fail_test, index=test_df.index)
    print(f"{'BIN':<12} {'N':>8} {'PRECISION':>10} {'RECALL':>8} {'F1':>6}")
    print("-" * 48)
    for lo, hi in BIN_EDGES:
        mask = test_df["SIM_ACHIEVED_COVERAGE"].between(lo, hi, inclusive="right")
        if not mask.any():
            continue
        y_bin = test_df.loc[mask, "PASS"].values
        proba_bin = proba_fail_series[mask].values
        pb, rb, f1b, nb = fail_metrics(y_bin, proba_bin, chosen_threshold)
        print(f"{lo}-{hi}%{'':<7} {mask.sum():>8,} {pb:>10.3f} {rb:>8.3f} {f1b:>6.3f}")

    # ── Save experimental model — separate file, best_model.pkl untouched ─────
    report_dict = classification_report(
        (y_test == 0).astype(int), (proba_fail_test >= chosen_threshold).astype(int),
        target_names=["Pass", "Fail"], output_dict=True,
    )
    model_package = {
        "model":                 deployed,
        "features":              FEATURES,
        "subject_difficulty":    subject_difficulty,
        "safe_subjects":         safe_subjects,
        "trained_on":            "23.2 to 25.2 excluding 23.1 pilot period (simulated multi-snapshot progress)",
        "validated_on":          "25.3",
        "accuracy":              float(round(report_dict["accuracy"], 4)),
        "model_name":            "XGBoost + Random Forest Ensemble (simulated progress)",
        "trained_at":            datetime.now(timezone.utc).isoformat(),
        "decision_threshold":    chosen_threshold,
        "classification_report": report_dict,
        "methodology":           "simulated_multi_snapshot_progress",
        "deployed":              False,
    }
    joblib.dump(model_package, MODEL_OUT)

    print("\n" + "═" * 70)
    print("NOT DEPLOYED")
    print("═" * 70)
    print(f"Saved to {MODEL_OUT} — backend/app/ml/best_model.pkl was NOT overwritten.")
    print(
        "This model was trained to interpret PARTIAL_WEIGHTED_SCORE as a cumulative\n"
        "sum across however many items are truncated-in (15-90% coverage), not the\n"
        "top-2-by-weight sum best_model.pkl expects. predictor.py's\n"
        "compute_partial_score() and main.py's roster endpoint still compute the\n"
        "top-2 version. Swapping best_model.pkl for this one without also updating\n"
        "those would silently miscalibrate every real prediction made from a\n"
        "complete (100%-coverage) record — the dominant real use case today, since\n"
        "this dataset has no genuine mid-term data yet. That's a deliberate decision\n"
        "left to you, not made silently here."
    )


if __name__ == "__main__":
    main()

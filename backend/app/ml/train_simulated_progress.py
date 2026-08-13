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

import numpy as np
import pandas as pd
from datetime import datetime, timezone
from imblearn.over_sampling import SMOTE
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_score, recall_score, f1_score, classification_report, roc_auc_score
from xgboost import XGBClassifier

from app.ml.train_model import (
    prepare_data_3way, prepare_data, build_simulated_progress_features, FEATURES,
)
from app.ml.sim_model_registry import register_version
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

    # ── Step B2: fit a Platt-scaling calibrator on the SAME out-of-sample ─────
    # validation predictions used above (val_model, fit on train-only, has
    # never seen these rows) — this model's raw P(fail) is known to
    # understate true pass likelihood (see model_card.md's calibration
    # check). Fitting on out-of-sample predictions, not the training set's
    # own (in-sample, overconfident) predictions, avoids the calibrator
    # itself being miscalibrated by leakage.
    print("\n" + "═" * 70)
    print("STEP B2 — Fitting Platt-scaling calibrator on out-of-sample validation predictions")
    print("═" * 70)
    true_fail_val = (y_val == 0).astype(int)
    calibrator = LogisticRegression()
    calibrator.fit(proba_fail_val.reshape(-1, 1), true_fail_val)
    # Because Platt scaling is a strictly-monotonic sigmoid, thresholding the
    # CALIBRATED probability at calibrator(chosen_threshold) flags EXACTLY
    # the same set of records as thresholding the RAW probability at
    # chosen_threshold — the Fail/Pass decision, recall, and precision are
    # therefore mathematically unchanged by calibration. Only the displayed
    # number changes. Recorded here so predictor.py can keep _compute_risk_band
    # internally consistent if it ever displays the calibrated probability.
    calibrated_decision_threshold = float(
        calibrator.predict_proba(np.array([[chosen_threshold]]))[0, 1]
    )
    print(f"Raw decision threshold (fail proba):        {chosen_threshold:.4f}")
    print(f"Calibrated equivalent (fail proba):         {calibrated_decision_threshold:.4f}")
    print("(Same underlying decision boundary — monotonic transform preserves which records are flagged.)")

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

    # ── Step E: calibration reliability check on TEST, before vs. after ───────
    # Applies the Step B2 calibrator (fit on validation, never on TEST) to
    # the deployed model's TEST predictions — genuinely out-of-sample for
    # both the base model and the calibrator.
    print("\n" + "═" * 70)
    print("STEP E — Calibration reliability check (raw vs. Platt-scaled), TEST period 25.3")
    print("═" * 70)
    true_fail_test  = (y_test == 0).astype(int)
    proba_pass_test = 1 - proba_fail_test
    true_pass_test  = 1 - true_fail_test
    calibrated_proba_fail_test = calibrator.predict_proba(proba_fail_test.reshape(-1, 1))[:, 1]
    calibrated_proba_pass_test = 1 - calibrated_proba_fail_test

    def _reliability(proba_pass, true_pass_arr, title):
        bins = [(0, 10), (10, 20), (20, 30), (30, 40), (40, 50),
                (50, 60), (60, 70), (70, 80), (80, 90), (90, 100)]
        print(f"\n{title}")
        print(f"{'Predicted P(Pass)':<20}{'N':>8}{'Actual pass rate':>20}")
        rows = []
        for lo, hi in bins:
            mask = (proba_pass * 100 >= lo) & (proba_pass * 100 <= hi if hi == 100 else proba_pass * 100 < hi)
            n = int(mask.sum())
            if n == 0:
                continue
            actual = float(true_pass_arr[mask].mean() * 100)
            rows.append((lo, hi, n, actual))
            print(f"{lo}-{hi}%{'':<15}{n:>8}{actual:>19.1f}%")
        total_n = sum(n for _, _, n, _ in rows)
        mace = sum(n * abs(((lo + hi) / 2) - actual) for lo, hi, n, actual in rows) / total_n
        print(f"Mean absolute calibration error (N-weighted): {mace:.2f}pp")
        return mace

    mace_before = _reliability(proba_pass_test, true_pass_test, "BEFORE (raw, uncalibrated)")
    mace_after  = _reliability(calibrated_proba_pass_test, true_pass_test, "AFTER Platt scaling")
    auc_before  = roc_auc_score(true_fail_test, proba_fail_test)
    auc_after   = roc_auc_score(true_fail_test, calibrated_proba_fail_test)
    print(f"\nROC-AUC before: {auc_before:.4f}  |  after: {auc_after:.4f}  "
          f"(should be ~identical — calibration is monotonic, doesn't change ranking)")
    print(f"\nCalibration Safe-floor consequence: raw threshold {chosen_threshold:.4f} (fail proba) "
          f"corresponds to a CALIBRATED fail proba of {calibrated_decision_threshold:.4f} — "
          f"if the risk-band Safe floor were derived from the calibrated threshold instead of the "
          f"raw one, it would move from {max(65, 100*(1-chosen_threshold)):.0f}% to "
          f"{max(65, 100*(1-calibrated_decision_threshold)):.0f}%, not converge with the "
          f"complete-record model's 65% floor. See model_card.md for the full writeup — "
          f"this is why the calibrator is saved for use as an ADDITIONAL field, not swapped in "
          f"as a silent replacement for the existing risk_band logic.")

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
        # Calibration correction (Round 4 close-out) — fit on out-of-sample
        # validation predictions (Step B2), never on TEST. NOT wired into
        # predict_partial()'s existing "probability"/"prediction"/"risk_band"
        # fields — see predictor.py's "probability_calibrated" field and
        # model_card.md's writeup for why a silent swap isn't done here.
        "calibrator":                     calibrator,
        "calibrated_decision_threshold":  calibrated_decision_threshold,
        "calibration_mace_before_pp":     round(mace_before, 2),
        "calibration_mace_after_pp":      round(mace_after, 2),
        "train_row_count":                len(X_train_full),
    }

    # Registered as a new version — NOT written to best_model_simulated_progress.pkl
    # directly and NOT made live automatically. This used to overwrite that file
    # in place, live immediately, no comparison, no versioning, no human review —
    # a real gap found and fixed urgently after an attendance-feature retrain went
    # live ungated with no way to compare it against what was previously serving.
    # Run compare_and_promote_simulated.py to review this version against whatever
    # is currently live and promote it explicitly.
    version = register_version(model_package, {
        "trained_at":            model_package["trained_at"],
        "accuracy":              model_package["accuracy"],
        "decision_threshold":    model_package["decision_threshold"],
        "classification_report": model_package["classification_report"],
        "train_row_count":       model_package["train_row_count"],
        "trained_on":            model_package["trained_on"],
        "validated_on":          model_package["validated_on"],
        "model_name":            model_package["model_name"],
        "features":              model_package["features"],
    })

    print("\n" + "═" * 70)
    print("NOT LIVE — registered as a new version only")
    print("═" * 70)
    print(f"  ✓ Model registered as version {version} (train rows: {len(X_train_full):,}) — NOT yet live.")
    print(f"    Run: python -m app.ml.compare_and_promote_simulated {version}")
    print("    to compare it against the live version and promote it if it's not meaningfully worse.")
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

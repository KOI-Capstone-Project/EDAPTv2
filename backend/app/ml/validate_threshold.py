"""
EDAPT v2 — Honest threshold selection via a held-out validation split.

FAIL_THRESHOLD (train_model.py) was originally chosen by sweeping thresholds
directly against the TEST set (the old approach, since removed as unused
during a codebase cleanup — its role is preserved here as history). That's
test-set leakage for a tuning decision: the precision/recall reported for a threshold
could be optimistic simply because it was the best-looking option *for that
specific test set*, not necessarily the best choice in general.

This script does it properly:
  1. Fit a model on TRAIN ONLY (everything before the validation period —
     see train_model.resolve_periods()) — it never sees the validation or
     test period.
  2. Sweep thresholds against VALIDATION predictions from that model. Pick
     the threshold that best satisfies the same criterion used originally
     (recall in the 0.80-0.85 band, maximise precision within it).
  3. Apply that validation-selected threshold to the ACTUALLY-LIVE model
     (loaded via model_registry, not a hardcoded best_model.pkl path — that
     file stops being current the moment any retrain happens under the
     versioning system) and report precision/recall/F1 on the untouched
     TEST set.
  4. Compare that to the currently-configured FAIL_THRESHOLD's numbers on
     the same test set, to show directly whether the current threshold was
     overfit to test, and by how much.

Train/validation/test periods are whatever train_model.resolve_periods()
currently resolves them to — never hardcoded here. As the dynamic period
resolution moves training forward to new terms, this script's periods move
with it automatically.

Usage (run from backend/, as a module — needed so its imports resolve the
same way whether run standalone or imported by scheduled_retrain.py):
    python -m app.ml.validate_threshold    # this script
"""

from imblearn.over_sampling import SMOTE
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.metrics import precision_score, recall_score, f1_score
from xgboost import XGBClassifier

from app.ml.train_model import prepare_data_3way, prepare_data, FAIL_THRESHOLD
from app.ml.model_registry import load_live_model

THRESHOLDS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]

# Same magnitude as compare_and_promote.py's regression gate, applied to the
# threshold value itself here rather than to precision/recall — the same
# "3pp is inside this dataset's period-to-period noise, not a real signal"
# reasoning established there.
MEANINGFUL_THRESHOLD_SHIFT = 0.03


def fail_metrics(y_true_pass, proba_fail, threshold):
    pred_fail = (proba_fail >= threshold).astype(int)
    true_fail = (y_true_pass == 0).astype(int)
    return (
        precision_score(true_fail, pred_fail, zero_division=0),
        recall_score(true_fail, pred_fail, zero_division=0),
        f1_score(true_fail, pred_fail, zero_division=0),
        int(pred_fail.sum()),
    )


def run_validation_sweep(verbose: bool = True) -> dict:
    """
    Runs the full honest-threshold-selection process and returns a result
    dict — callers (e.g. scheduled_retrain.py) can act on the finding
    programmatically instead of just reading console output. Never touches
    FAIL_THRESHOLD itself; that stays a human decision.
    """
    def _p(*a):
        if verbose:
            print(*a)

    # ── Step A: fit a TRAIN-ONLY model (never sees validation or test) ──────
    _p("═" * 70)
    _p("STEP A — Fitting a train-only model for honest threshold selection")
    _p("═" * 70)
    X_train, y_train, X_val, y_val, X_test_unused, y_test_unused, val_df, test_df_unused, _, _ = prepare_data_3way()
    val_period  = str(val_df["STUDYPERIOD"].iloc[0])
    test_period = str(test_df_unused["STUDYPERIOD"].iloc[0])
    _p(f"Resolved periods — validate={val_period}  test={test_period}")

    smote = SMOTE(random_state=42)
    X_res, y_res = smote.fit_resample(X_train, y_train)

    # Same hyperparameters as train_model.py's Step 4 — only the training data differs.
    xgb = XGBClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        random_state=42, eval_metric="logloss", verbosity=0,
    )
    rf = RandomForestClassifier(
        n_estimators=200, max_depth=6, class_weight="balanced",
        random_state=42, n_jobs=-1,
    )
    val_model = VotingClassifier(estimators=[("xgb", xgb), ("rf", rf)], voting="soft")
    val_model.fit(X_res, y_res)
    _p("Train-only model fitted.\n")

    # ── Step B: sweep thresholds against VALIDATION ──────────────────────────
    _p("═" * 70)
    _p(f"STEP B — Threshold sweep on VALIDATION ({val_period}), using the train-only model")
    _p("═" * 70)
    proba_fail_val = val_model.predict_proba(X_val)[:, 0]  # classes_ == [0,1] == [Fail,Pass]
    _p(f"Validation set: {len(y_val):,} rows ({int((y_val==0).sum()):,} fail / {int((y_val==1).sum()):,} pass)\n")

    _p(f"{'Threshold':>10}  {'Precision':>10}  {'Recall':>8}  {'F1':>6}  {'Flagged as Fail':>16}")
    _p("-" * 62)
    val_results = []
    for t in THRESHOLDS:
        p, r, f1, n = fail_metrics(y_val, proba_fail_val, t)
        val_results.append((t, p, r, f1, n))
        _p(f"{t:>10.2f}  {p:>10.3f}  {r:>8.3f}  {f1:>6.3f}  {n:>16,}")

    band = [row for row in val_results if 0.80 <= row[2] <= 0.85]
    if band:
        chosen = max(band, key=lambda row: row[1])
    else:
        # fall back to the closest-to-band threshold if nothing lands exactly inside it
        chosen = min(val_results, key=lambda row: min(abs(row[2] - 0.80), abs(row[2] - 0.85)))
    chosen_threshold = chosen[0]
    _p(f"\nSelected on validation: threshold={chosen_threshold:.2f}  "
       f"(precision={chosen[1]:.3f}, recall={chosen[2]:.3f}, f1={chosen[3]:.3f})")

    # ── Step C: apply the validation-selected threshold to the LIVE model,
    #            report on the untouched TEST set ────────────────────────────
    _p("\n" + "═" * 70)
    _p(f"STEP C — Applying validation-selected threshold to the LIVE model, on TEST ({test_period})")
    _p("═" * 70)
    live_package = load_live_model()
    if live_package is None:
        raise RuntimeError("No live model in the registry — run train_model.py and promote a version first.")
    deployed = live_package["model"]
    _, _, X_test, y_test, test_df, _, _ = prepare_data()  # live model's own train/test split
    proba_fail_test = deployed.predict_proba(X_test)[:, 0]

    p_new, r_new, f1_new, n_new = fail_metrics(y_test, proba_fail_test, chosen_threshold)
    p_cur, r_cur, f1_cur, n_cur = fail_metrics(y_test, proba_fail_test, FAIL_THRESHOLD)

    _p(f"\nOn TEST ({test_period}), live model, {len(y_test):,} rows:")
    _p(f"  Validation-selected threshold {chosen_threshold:.2f}:  precision={p_new:.3f}  recall={r_new:.3f}  f1={f1_new:.3f}")
    _p(f"  Currently-configured FAIL_THRESHOLD {FAIL_THRESHOLD:.2f}:  precision={p_cur:.3f}  recall={r_cur:.3f}  f1={f1_cur:.3f}")

    threshold_delta      = chosen_threshold - FAIL_THRESHOLD
    meaningfully_shifted = abs(threshold_delta) > MEANINGFUL_THRESHOLD_SHIFT

    _p("\n" + "═" * 70)
    _p("CONCLUSION")
    _p("═" * 70)
    if abs(threshold_delta) < 1e-9:
        _p(f"Validation selected the SAME threshold ({FAIL_THRESHOLD}) independently of the test set.")
        _p(f"FAIL_THRESHOLD={FAIL_THRESHOLD} was not an artifact of tuning against the test set — it holds up.")
    elif not meaningfully_shifted:
        _p(f"Validation selected threshold={chosen_threshold:.2f} vs. the current FAIL_THRESHOLD={FAIL_THRESHOLD:.2f} "
           f"— a {threshold_delta:+.2f} difference, within the {MEANINGFUL_THRESHOLD_SHIFT:.2f} noise band.")
        _p("Not meaningfully shifted — the current FAIL_THRESHOLD still holds up.")
    else:
        _p(f"⚠ Validation selected threshold={chosen_threshold:.2f} vs. the current FAIL_THRESHOLD={FAIL_THRESHOLD:.2f} "
           f"— a {threshold_delta:+.2f} difference, beyond the {MEANINGFUL_THRESHOLD_SHIFT:.2f} noise band.")
        _p("MEANINGFULLY SHIFTED — worth a human decision on whether to update FAIL_THRESHOLD. "
           "Not changed automatically.")

    return {
        "val_period":            val_period,
        "test_period":           test_period,
        "current_fail_threshold": FAIL_THRESHOLD,
        "chosen_threshold":       chosen_threshold,
        "threshold_delta":        threshold_delta,
        "meaningfully_shifted":   meaningfully_shifted,
        "test_metrics_at_chosen": {"precision": p_new, "recall": r_new, "f1": f1_new},
        "test_metrics_at_current": {"precision": p_cur, "recall": r_cur, "f1": f1_cur},
    }


def main() -> None:
    run_validation_sweep(verbose=True)


if __name__ == "__main__":
    main()

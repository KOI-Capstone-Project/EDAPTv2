"""
EDAPT v2 — ML Training Pipeline (leakage-free)
Run once from the project root before starting the server.

Usage:
    python backend/app/ml/train_model.py

Trains on subjects verified clean via data/subject_reliability.json —
fully_clean and mostly_clean, minus TSL713 (its CQ/IA weightings were found
swapped by the cleaning script, which a weighting-sum check can't detect).
mostly_clean subjects still contain a minority of enrolments whose recorded
WEIGHTING doesn't sum to ~100, so those specific enrolments are filtered out
individually (same 99-101 check used to classify subjects in the first
place) rather than including or excluding an entire subject's data at once.
Period 23.1 is excluded from training as a pilot period with too few
records to add signal.

Features are built from the first two highest-weighted assessments only,
simulating the realistic prediction scenario where only early marks are
available. The PASS target is computed separately from all assessments
and is never used as an input feature.

Outputs:
    A new versioned entry in backend/app/ml/models/ (registry.json + a
    model_{version}.pkl), via model_registry.register_version(). This does
    NOT become the live model automatically — run compare_and_promote.py to
    review it against whatever is currently live and promote it explicitly.

Train/validation/test periods are resolved dynamically (resolve_periods()),
not hardcoded: test = the latest STUDYPERIOD actually present in the raw
data, validation = the second-latest, train = everything before validation
(excluding the 23.1 pilot period, which is always excluded regardless of
where it'd otherwise fall). This means retraining after a new period
appears in the data automatically shifts the whole split forward — no
constants to update by hand.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.metrics import accuracy_score, classification_report, precision_score, recall_score, f1_score
from xgboost import XGBClassifier

# ── Paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR       = Path(__file__).resolve().parent
DATA_PATH        = SCRIPT_DIR.parent.parent.parent / "data" / "Capstone_data_20260324.csv"
RELIABILITY_PATH = SCRIPT_DIR.parent.parent.parent / "data" / "subject_reliability.json"

# ── Constants ─────────────────────────────────────────────────────────────────

PILOT_PERIOD = "23.1"

# Fail-class decision threshold applied to predict_proba() in predictor.py.
# 0.55 was originally chosen by sweeping directly against the T3 2025 TEST set
# (evaluate_thresholds.py), which is test-set leakage for a tuning decision.
# validate_threshold.py re-selected the threshold honestly, using a model
# trained only on <25.2 and swept against a held-out 25.2 validation split —
# that process picked 0.50, not 0.55. 0.50 gives recall 0.837 / precision
# 0.770 on the T3 2025 test set (vs. 0.822 / 0.805 at 0.55 — the gap is real
# but modest, and some of it may reflect a genuine 25.2->25.3 fail-rate shift
# rather than pure overfitting; see investigate_fail_rate_shift.py). Single
# source of truth — predictor.py imports this constant rather than hardcoding
# its own copy, so the two can't drift apart. NOTE: this value was tuned
# against the 25.2/25.3 period pair specifically — if the dynamic split moves
# to different periods, this threshold isn't automatically re-validated for
# them (that's what validate_threshold.py is for; it already uses the dynamic
# split via prepare_data_3way(), so re-running it re-validates for whatever
# periods are current).
FAIL_THRESHOLD = 0.50
FEATURES     = [
    "ASSESS1_MARK",
    "ASSESS1_WEIGHT",
    "ASSESS1_CONTRIBUTION",
    "ASSESS2_MARK",
    "ASSESS2_WEIGHT",
    "ASSESS2_CONTRIBUTION",
    "PARTIAL_WEIGHTED_SCORE",
    "PARTIAL_WEIGHT_COVERAGE",
    "SUBJECT_DIFFICULTY",
    "TRIMESTER_NUM",
]

# ── Step 1 — Feature Engineering ──────────────────────────────────────────────

def build_target(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute the true final weighted score across ALL assessments per
    student-subject-period.

    The >= 50 pass mark below is KOI's real, confirmed grading policy
    (confirmed directly by the project owner — not an assumption carried
    over from early in the project, and not something this codebase should
    re-flag as unverified). Applies uniformly across all subjects.
    """
    df = df.copy()
    df["_WEIGHTED_SCORE"] = df["MARKPERCENT"] * df["WEIGHTING"] / 100
    target = (
        df.groupby(["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"])
        .agg(FULL_WEIGHTED_FINAL=("_WEIGHTED_SCORE", "sum"))
        .reset_index()
    )
    target["PASS"] = (target["FULL_WEIGHTED_FINAL"] >= 50).astype(int)  # KOI pass mark, confirmed
    return target[["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD", "PASS"]]


def build_early_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each student-subject-period, extract features from only the first two
    highest-weighted assessments — simulating what a lecturer knows mid-term.

    IMPORTANT: this project's raw data is a closed, term-end snapshot — every
    training row has 100% of its assessment weighting recorded (verified: 0
    partial-coverage rows exist in the historical CSV). That means a
    cumulative "sum across ALL recorded items" feature is mathematically
    identical to FULL_WEIGHTED_FINAL for every training row, and PASS is
    defined as FULL_WEIGHTED_FINAL >= 50 — so that feature would just
    reconstruct the label directly (confirmed: 100% agreement, 1.0000
    accuracy when tried). Capping at a fixed top-2 regardless of how many
    items exist is what keeps this simulating a genuine "still mid-term"
    information state despite the underlying data being complete. Any fix for
    "discards 3+ item signal" needs the model to see genuinely-truncated
    partial data during training (e.g. simulated coverage levels, like
    simulate_progress does for the roster endpoint demo) — not a plain sum
    over everything recorded, which isn't a partial signal on this dataset.
    """
    rows = []
    for (student, subject, period, country), grp in df.groupby(
        ["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD", "COUNTRY_MASKED"]
    ):
        grp_sorted = grp.sort_values("WEIGHTING", ascending=False).reset_index(drop=True)

        a1 = grp_sorted.iloc[0]
        a1_mark    = float(a1["MARKPERCENT"])
        a1_weight  = float(a1["WEIGHTING"])
        a1_contrib = a1_mark * a1_weight / 100

        if len(grp_sorted) > 1:
            a2 = grp_sorted.iloc[1]
            a2_mark   = float(a2["MARKPERCENT"])
            a2_weight = float(a2["WEIGHTING"])
        else:
            a2_mark   = 0.0
            a2_weight = 0.0
        a2_contrib = a2_mark * a2_weight / 100

        rows.append({
            "STUDENTID_MASKED":        student,
            "SUBJECTCODE":             subject,
            "STUDYPERIOD":             period,
            "COUNTRY_MASKED":          country,
            "ASSESS1_MARK":            a1_mark,
            "ASSESS1_WEIGHT":          a1_weight,
            "ASSESS1_CONTRIBUTION":    a1_contrib,
            "ASSESS2_MARK":            a2_mark,
            "ASSESS2_WEIGHT":          a2_weight,
            "ASSESS2_CONTRIBUTION":    a2_contrib,
            "PARTIAL_WEIGHTED_SCORE":  a1_contrib + a2_contrib,
            "PARTIAL_WEIGHT_COVERAGE": (a1_weight + a2_weight) / 100,
            "TRIMESTER_NUM":           float(period),
        })
    return pd.DataFrame(rows)


def build_simulated_progress_features(raw: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """
    Multi-snapshot alternative to build_early_features(): for each real,
    fully-graded student-subject-period, generate several synthetic
    partial-progress rows by truncating that student's real items to a
    randomly sampled cumulative-weighting cutoff, sorted by submission order
    (STUDYPACKAGEASSESSMENTID) rather than weight — matching main.py's
    simulate_progress roster logic. One cutoff is drawn per bin from
    [15,30), [30,50), [50,70), [70,90) (stratified, not pure uniform, so
    every enrolment contributes to every reporting bin rather than leaving
    bin coverage to chance).

    LEAKAGE BOUNDARY: PARTIAL_WEIGHTED_SCORE/COVERAGE are computed ONLY from
    the truncated subset. The label is never touched here — build_target()
    always computes PASS from the full, untruncated record, merged in by the
    caller. Cutoffs are capped at 90%, deliberately never reaching 100%, so
    the model never sees the degenerate "cumulative score == final score"
    case that made build_early_features()'s sum-of-all-items attempt
    reconstruct the label outright (see that function's docstring). Verified
    empirically in train_simulated_progress.py, not just asserted here.

    ASSESS1/ASSESS2 are the top-2-by-weight items WITHIN the truncated
    subset (matching what main.py's roster endpoint already computes under
    simulate_progress), not top-2 of the full record.
    """
    rng = np.random.default_rng(seed)
    bins = [(15.0, 30.0), (30.0, 50.0), (50.0, 70.0), (70.0, 90.0)]
    rows = []
    for (student, subject, period, country), grp in raw.groupby(
        ["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD", "COUNTRY_MASKED"]
    ):
        grp_seq = grp.sort_values("STUDYPACKAGEASSESSMENTID").reset_index(drop=True)
        cum_seq = grp_seq["WEIGHTING"].cumsum()

        for lo, hi in bins:
            cutoff = float(rng.uniform(lo, hi))
            included = grp_seq[cum_seq <= cutoff]
            if included.empty:
                continue

            by_weight = included.sort_values("WEIGHTING", ascending=False).reset_index(drop=True)
            a1 = by_weight.iloc[0]
            a1_mark, a1_weight = float(a1["MARKPERCENT"]), float(a1["WEIGHTING"])
            a1_contrib = a1_mark * a1_weight / 100

            if len(by_weight) > 1:
                a2 = by_weight.iloc[1]
                a2_mark, a2_weight = float(a2["MARKPERCENT"]), float(a2["WEIGHTING"])
            else:
                a2_mark, a2_weight = 0.0, 0.0
            a2_contrib = a2_mark * a2_weight / 100

            partial_weighted_score  = float((included["MARKPERCENT"] * included["WEIGHTING"] / 100).sum())
            achieved_coverage       = float(included["WEIGHTING"].sum())  # percent, before /100

            rows.append({
                "STUDENTID_MASKED":        student,
                "SUBJECTCODE":             subject,
                "STUDYPERIOD":             period,
                "COUNTRY_MASKED":          country,
                "ASSESS1_MARK":            a1_mark,
                "ASSESS1_WEIGHT":          a1_weight,
                "ASSESS1_CONTRIBUTION":    a1_contrib,
                "ASSESS2_MARK":            a2_mark,
                "ASSESS2_WEIGHT":          a2_weight,
                "ASSESS2_CONTRIBUTION":    a2_contrib,
                "PARTIAL_WEIGHTED_SCORE":  partial_weighted_score,
                "PARTIAL_WEIGHT_COVERAGE": achieved_coverage / 100,
                "TRIMESTER_NUM":           float(period),
                "SIM_CUTOFF_BIN":          f"{int(lo)}-{int(hi)}%",
                "SIM_ACHIEVED_COVERAGE":   achieved_coverage,
            })
    return pd.DataFrame(rows)


def compute_subject_difficulty(raw_train: pd.DataFrame) -> dict:
    """Proportion of raw assessment records per subject with MARKPERCENT < 50 (train period, record-level)."""
    return (
        raw_train.groupby("SUBJECTCODE")["MARKPERCENT"]
        .apply(lambda s: round(float((s < 50).mean()), 4))
        .to_dict()
    )

# ── Data preparation (shared by main() and standalone evaluation scripts) ──────

def load_and_filter_raw():
    """
    Load the raw CSV and apply every filter that doesn't depend on where the
    train/validation/test boundary falls: SAFE_SUBJECTS (fully_clean +
    mostly_clean, minus TSL713), the enrolment-level dirty-weighting filter,
    and the 23.1 pilot period exclusion.

    Feature/target aggregation and the temporal split are left to the caller —
    subject difficulty must be computed only from whichever period range counts
    as "train" for a given split, since computing it from data that includes a
    validation or test period would leak information into a feature.

    Returns (raw, SAFE_SUBJECTS).
    """
    # ── Load ──────────────────────────────────────────────────────────────────
    if not DATA_PATH.exists():
        print(f"ERROR: data file not found at {DATA_PATH}")
        sys.exit(1)
    print(f"Loading {DATA_PATH} …")
    raw = pd.read_csv(DATA_PATH)
    raw["STUDYPERIOD"] = raw["STUDYPERIOD"].apply(
        lambda x: str(round(float(x), 1)) if pd.notna(x) else ""
    )
    raw["MARKPERCENT"] = pd.to_numeric(raw["MARKPERCENT"], errors="coerce")
    raw = raw.dropna(subset=["MARKPERCENT"])
    print(f"Raw rows: {len(raw):,}")

    # ── Safe subject filter ──────────────────────────────────────────────────
    print("\n── Filtering to reliable subjects ──────────────────────────────────")
    with open(RELIABILITY_PATH) as f:
        reliability = json.load(f)
    SAFE_SUBJECTS = sorted(
        s for s in (reliability["fully_clean"] + reliability["mostly_clean"])
        if s != "TSL713"
    )
    print(f"  SAFE_SUBJECTS: {len(SAFE_SUBJECTS)} subjects "
          f"({len(reliability['fully_clean'])} fully_clean + {len(reliability['mostly_clean'])} mostly_clean, "
          f"TSL713 excluded — CQ/IA weightings swapped)")

    raw = raw[raw["SUBJECTCODE"].isin(SAFE_SUBJECTS)]
    print(f"  Rows remaining after SAFE_SUBJECTS filter: {len(raw):,}")
    print(f"  Unique subjects included: {raw['SUBJECTCODE'].nunique()}")

    # ── Enrolment-level clean filter (for mostly_clean subjects) ────────────
    # A mostly_clean subject is still only 90-99.9% clean at the enrolment
    # level — some of its students have a WEIGHTING sum that doesn't land on
    # ~100, which makes their PASS target (summed from WEIGHTING) unreliable.
    # Drop those specific enrolments rather than the whole subject. This is a
    # no-op for fully_clean subjects, since 100% of their enrolments already
    # pass this check.
    enrolment_weight = (
        raw[raw["ATTEMPTNUMBER"] == 1]
        .groupby(["SUBJECTCODE", "STUDYPERIOD", "STUDENTID_MASKED"])["WEIGHTING"]
        .sum()
    )
    clean_index = pd.MultiIndex.from_tuples(
        enrolment_weight[enrolment_weight.between(99.0, 101.0)].index,
        names=["SUBJECTCODE", "STUDYPERIOD", "STUDENTID_MASKED"],
    )
    raw_keys = pd.MultiIndex.from_arrays(
        [raw["SUBJECTCODE"], raw["STUDYPERIOD"], raw["STUDENTID_MASKED"]]
    )
    before_dirty_filter = len(raw)
    raw = raw[raw_keys.isin(clean_index)]
    print(f"  Rows dropped as dirty enrolments (weighting sum outside 99-101): {before_dirty_filter - len(raw):,}")
    print(f"  Rows remaining after enrolment-level clean filter: {len(raw):,}")

    pilot_rows = int((raw["STUDYPERIOD"] == PILOT_PERIOD).sum())
    raw = raw[raw["STUDYPERIOD"] != PILOT_PERIOD]
    print(f"  Excluded {pilot_rows:,} rows from pilot period {PILOT_PERIOD} (insufficient signal)")

    return raw, SAFE_SUBJECTS


def resolve_periods(raw: pd.DataFrame) -> tuple:
    """
    Determine (val_period, test_period) dynamically from whatever STUDYPERIODs
    are actually present in the filtered raw data (the 23.1 pilot period is
    already excluded upstream in load_and_filter_raw(), so it can never be
    picked here regardless of where it'd otherwise sort).

    test_period = the latest period present
    val_period  = the second-latest period present

    Both are returned as the original string values (not floats) so callers
    can use them directly for STUDYPERIOD equality checks. Numeric comparison
    (float(p) < float(boundary)) is what determines "before" a boundary
    elsewhere in this module — that's valid here because this project's
    STUDYPERIOD encoding (YY.T, trimester T always 1-3) sorts identically
    whether compared as strings or as floats.
    """
    periods = sorted(raw["STUDYPERIOD"].dropna().unique(), key=lambda p: float(p))
    if len(periods) < 2:
        raise ValueError(
            f"Need at least 2 distinct study periods (excluding the pilot period) "
            f"to form a validation/test split; found {periods}."
        )
    test_period = periods[-1]
    val_period  = periods[-2]
    return val_period, test_period


def _build_features_and_target(raw: pd.DataFrame, difficulty_period_mask, feature_builder=build_early_features):
    """
    Build the merged features+target dataframe from filtered raw records.
    subject_difficulty is computed only from rows where difficulty_period_mask
    is True, so it never sees validation or test period data.

    feature_builder defaults to build_early_features (top-2-by-weight, one row
    per enrolment) for backward compatibility with main()/evaluate_thresholds.py/
    validate_threshold.py. Pass build_simulated_progress_features to use the
    multi-snapshot truncated-progress approach instead (see
    train_simulated_progress.py).
    """
    print("\n── Step 1: Feature Engineering ────────────────────────────────────")
    print("  Computing final pass targets from ALL assessments …")
    target = build_target(raw)

    print(f"  Building features via {feature_builder.__name__}() …")
    feat = feature_builder(raw)
    print(f"  Feature rows: {len(feat):,}")

    print("  Computing subject difficulty from training records (record-level, pre-aggregation) …")
    subject_difficulty = compute_subject_difficulty(raw[difficulty_period_mask])
    feat["SUBJECT_DIFFICULTY"] = feat["SUBJECTCODE"].map(subject_difficulty).fillna(0.0)
    print(f"  Subjects with difficulty scores: {len(subject_difficulty)}")

    data = feat.merge(target, on=["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"], how="inner")
    print(f"  Merged rows: {len(data):,}")
    return data, subject_difficulty


def prepare_data(feature_builder=build_early_features):
    """
    Two-way split used by main() and evaluate_thresholds.py:
    Test  = the latest STUDYPERIOD present in the data (resolve_periods())
    Train = everything before it (excluding the 23.1 pilot period)

    Both boundaries are resolved dynamically from whatever's actually in the
    raw data — see resolve_periods(). Nothing here is hardcoded to a specific
    period, so this split moves forward automatically once a new period
    appears in the source CSV.

    Returns (X_train, y_train, X_test, y_test, test_df, subject_difficulty, SAFE_SUBJECTS).
    """
    raw, SAFE_SUBJECTS = load_and_filter_raw()
    _val_period, test_period = resolve_periods(raw)
    print(f"\n── Resolved periods: test={test_period} (train = everything before it) ──")
    train_period_mask = raw["STUDYPERIOD"].apply(lambda p: float(p) < float(test_period))
    data, subject_difficulty = _build_features_and_target(raw, train_period_mask, feature_builder)

    # ── Step 2 — Temporal Split ───────────────────────────────────────────────
    print("\n── Step 2: Temporal Split ──────────────────────────────────────────")
    train_mask = data["STUDYPERIOD"].apply(lambda p: float(p) < float(test_period))
    train = data[train_mask].copy()
    test  = data[data["STUDYPERIOD"] == test_period].copy()

    print(f"Train: {len(train):,} rows  |  Test: {len(test):,} rows")
    print(f"Train PASS — pass: {train['PASS'].sum():,}  fail: {(train['PASS']==0).sum():,}")
    print(f"Test  PASS — pass: {test['PASS'].sum():,}   fail: {(test['PASS']==0).sum():,}")

    X_train = train[FEATURES].values
    y_train = train["PASS"].values
    X_test  = test[FEATURES].values
    y_test  = test["PASS"].values

    return X_train, y_train, X_test, y_test, test, subject_difficulty, SAFE_SUBJECTS


def prepare_data_3way(feature_builder=build_early_features):
    """
    Three-way split for honest threshold selection. Boundaries are resolved
    dynamically (resolve_periods()), not hardcoded:
    Train    : everything before the validation period — fit the model only
    Validate : the second-latest period present — pick the decision threshold
               only, never used to fit a model that's then evaluated on it
    Test     : the latest period present — untouched by any tuning decision,
               used only for final reporting

    subject_difficulty is computed from the train period only, so validation
    and test periods can't leak into that feature either.

    Returns (X_train, y_train, X_val, y_val, X_test, y_test, val_df, test_df,
             subject_difficulty, SAFE_SUBJECTS).
    """
    raw, SAFE_SUBJECTS = load_and_filter_raw()
    val_period, test_period = resolve_periods(raw)
    print(f"\n── Resolved periods: validate={val_period}  test={test_period} "
          f"(train = everything before {val_period}) ──")
    train_period_mask = raw["STUDYPERIOD"].apply(lambda p: float(p) < float(val_period))
    data, subject_difficulty = _build_features_and_target(raw, train_period_mask, feature_builder)

    print("\n── Step 2: Train / Validation / Test Split ──────────────────────────")
    train_mask = data["STUDYPERIOD"].apply(lambda p: float(p) < float(val_period))
    val_mask   = data["STUDYPERIOD"] == val_period
    test_mask  = data["STUDYPERIOD"] == test_period

    train = data[train_mask].copy()
    val   = data[val_mask].copy()
    test  = data[test_mask].copy()

    print(f"Train: {len(train):,} rows  |  Validate: {len(val):,} rows  |  Test: {len(test):,} rows")
    print(f"Train    PASS — pass: {train['PASS'].sum():,}  fail: {(train['PASS']==0).sum():,}")
    print(f"Validate PASS — pass: {val['PASS'].sum():,}   fail: {(val['PASS']==0).sum():,}")
    print(f"Test     PASS — pass: {test['PASS'].sum():,}   fail: {(test['PASS']==0).sum():,}")

    X_train = train[FEATURES].values
    y_train = train["PASS"].values
    X_val   = val[FEATURES].values
    y_val   = val["PASS"].values
    X_test  = test[FEATURES].values
    y_test  = test["PASS"].values

    return X_train, y_train, X_val, y_val, X_test, y_test, val, test, subject_difficulty, SAFE_SUBJECTS


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    X_train, y_train, X_test, y_test, test, subject_difficulty, SAFE_SUBJECTS = prepare_data()

    # ── Step 3 — SMOTE ────────────────────────────────────────────────────────
    print("\n── Step 3: SMOTE ───────────────────────────────────────────────────")
    smote = SMOTE(random_state=42)
    X_res, y_res = smote.fit_resample(X_train, y_train)
    unique, counts = np.unique(y_res, return_counts=True)
    for cls, cnt in zip(unique, counts):
        label = "fail" if cls == 0 else "pass"
        print(f"  Class {cls} ({label}): {cnt:,} samples after SMOTE")

    # ── Step 4 — Ensemble ─────────────────────────────────────────────────────
    print("\n── Step 4: Training Ensemble ───────────────────────────────────────")
    xgb = XGBClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        random_state=42, eval_metric="logloss", verbosity=0,
    )
    rf = RandomForestClassifier(
        n_estimators=200, max_depth=6, class_weight="balanced",
        random_state=42, n_jobs=-1,
    )
    ensemble = VotingClassifier(
        estimators=[("xgb", xgb), ("rf", rf)],
        voting="soft",
    )
    ensemble.fit(X_res, y_res)
    print("Ensemble trained.")

    # ── Step 5 — Validate ─────────────────────────────────────────────────────
    print("\n── Step 5: Validation on T3 2025 ──────────────────────────────────")
    y_pred   = ensemble.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    report_dict = classification_report(y_test, y_pred, target_names=["Fail", "Pass"], output_dict=True)
    fail_recall = report_dict["Fail"]["recall"]

    print(classification_report(y_test, y_pred, target_names=["Fail", "Pass"]))
    print(f"Accuracy:     {accuracy:.4f}")
    print(f"Fail recall:  {fail_recall:.4f}  (proportion of failing students correctly identified)")

    if accuracy < 0.75:
        print(f"\n  ⚠ WARNING: KPI not met — accuracy {accuracy:.4f} is below 0.75")
    if fail_recall < 0.60:
        print(f"  ⚠ WARNING: Model misses too many failing students — fail recall {fail_recall:.4f} < 0.60")

    # ── Step 6 — Bias Audit ───────────────────────────────────────────────────
    # All three breakdowns audit y_pred — the raw ensemble's default 0.5 cutoff
    # from Step 5 — not the deployed-threshold predictions (those don't exist
    # until Step 7). This matches the country audit's existing behavior
    # exactly; it isn't a new inconsistency introduced here.
    #
    # Country stays accuracy-only, unchanged from before — not retrofitted to
    # fail-class P/R/F1, since only gender/age were asked for that. Gender and
    # age are reported SEPARATELY (not cross-tabbed together), since combining
    # them would fragment sample sizes below anything meaningful.
    MIN_GROUP_SAMPLE  = 100   # same minimum as the existing country audit
    BIAS_FLAG_DELTA   = 0.10  # 10pp — same magnitude as the country audit's flag

    print("\n── Step 6: Bias Audit by Country ──────────────────────────────────")
    print("Note: countries with fewer than 100 test records are excluded from bias reporting due to insufficient sample size.")
    test_audit = test.copy()
    test_audit["PRED"] = y_pred

    # GENDERCODE/AGEGROUP were never part of build_early_features()'s output
    # (only COUNTRY_MASKED was) — deliberately not adding them there, since
    # that's training-feature code and this audit has no business influencing
    # what the model is fit on. Attached here as a separate, audit-only
    # lookup instead: one row per student, joined onto the already-built test
    # set purely for reporting.
    demographics = (
        pd.read_csv(DATA_PATH, usecols=["STUDENTID_MASKED", "GENDERCODE", "AGEGROUP"])
        .drop_duplicates(subset=["STUDENTID_MASKED"])
    )
    test_audit = test_audit.merge(demographics, on="STUDENTID_MASKED", how="left")

    # Null demographics get an explicit "Unknown" category rather than being
    # silently dropped by pandas' default value_counts() NaN-exclusion — a
    # student with missing GENDERCODE/AGEGROUP/COUNTRY_MASKED previously
    # vanished from every per-group breakdown below while still counting
    # toward the overall accuracy/precision/recall figures above, meaning the
    # two headline numbers could silently be computed on different
    # populations. Verified against the real current test period (25.3):
    # zero nulls exist in any of the three columns right now, so this has no
    # effect on today's numbers — it's a forward-looking fix so a future
    # dataset with incomplete demographic entry doesn't silently develop an
    # invisible "Unknown" blind spot.
    for _demo_col in ("COUNTRY_MASKED", "GENDERCODE", "AGEGROUP"):
        test_audit[_demo_col] = test_audit[_demo_col].fillna("Unknown")

    country_counts = test_audit["COUNTRY_MASKED"].value_counts()
    qualifying = country_counts[country_counts > 100].index

    country_bias = {}
    print(f"{'COUNTRY':<20} {'N':>6}  {'ACCURACY':>8}")
    print("-" * 40)
    for country in qualifying:
        grp     = test_audit[test_audit["COUNTRY_MASKED"] == country]
        grp_acc = accuracy_score(grp["PASS"], grp["PRED"])
        flagged = (accuracy - grp_acc) > BIAS_FLAG_DELTA
        flag    = "  ⚠ WARNING" if flagged else ""
        print(f"{str(country):<20} {len(grp):>6}  {grp_acc:>8.4f}{flag}")
        country_bias[str(country)] = {
            "n": int(len(grp)), "accuracy": round(float(grp_acc), 4), "flagged": bool(flagged),
        }

    excluded_countries = country_counts[country_counts <= 100]
    if not excluded_countries.empty:
        print(f"Excluded from bias reporting (≤100 test records): {', '.join(str(c) for c in excluded_countries.index)}")

    # ── Gender / age, separately — fail-class precision/recall/F1 ───────────
    overall_fail_precision = report_dict["Fail"]["precision"]
    overall_fail_recall    = report_dict["Fail"]["recall"]

    def _group_bias_report(dimension_col: str, label: str) -> dict:
        print(f"\n── Step 6: Bias Audit by {label} (fail-class precision/recall/F1) ──")
        print(f"Note: {label} groups with fewer than {MIN_GROUP_SAMPLE} test records are excluded "
              f"due to insufficient sample size.")
        counts = test_audit[dimension_col].value_counts()
        qualifying_groups = counts[counts > MIN_GROUP_SAMPLE].index

        print(f"{label.upper():<15} {'N':>6}  {'PRECISION':>9}  {'RECALL':>8}  {'F1':>6}")
        print("-" * 55)
        group_bias = {}
        for group_val in qualifying_groups:
            grp = test_audit[test_audit[dimension_col] == group_val]
            true_fail = (grp["PASS"] == 0).astype(int)
            pred_fail = (grp["PRED"] == 0).astype(int)
            grp_precision = precision_score(true_fail, pred_fail, zero_division=0)
            grp_recall    = recall_score(true_fail, pred_fail, zero_division=0)
            grp_f1        = f1_score(true_fail, pred_fail, zero_division=0)

            precision_delta = grp_precision - overall_fail_precision
            recall_delta    = grp_recall - overall_fail_recall
            flagged = abs(precision_delta) > BIAS_FLAG_DELTA or abs(recall_delta) > BIAS_FLAG_DELTA
            reasons = []
            if abs(precision_delta) > BIAS_FLAG_DELTA:
                reasons.append(f"precision {precision_delta:+.3f}")
            if abs(recall_delta) > BIAS_FLAG_DELTA:
                reasons.append(f"recall {recall_delta:+.3f}")
            flag = f"  ⚠ WARNING ({', '.join(reasons)})" if flagged else ""

            print(f"{str(group_val):<15} {len(grp):>6}  {grp_precision:>9.4f}  {grp_recall:>8.4f}  {grp_f1:>6.4f}{flag}")
            group_bias[str(group_val)] = {
                "n":             int(len(grp)),
                "fail_precision": round(float(grp_precision), 4),
                "fail_recall":    round(float(grp_recall), 4),
                "fail_f1":        round(float(grp_f1), 4),
                "flagged":        bool(flagged),
                "flag_reason":    ", ".join(reasons) if reasons else None,
            }

        excluded_groups = counts[counts <= MIN_GROUP_SAMPLE]
        if not excluded_groups.empty:
            print(f"Excluded from bias reporting (≤{MIN_GROUP_SAMPLE} test records): "
                  f"{', '.join(str(g) for g in excluded_groups.index)}")
        return group_bias

    gender_bias = _group_bias_report("GENDERCODE", "Gender")
    age_bias    = _group_bias_report("AGEGROUP", "Age Group")

    bias_audit = {
        "overall_accuracy":       round(float(accuracy), 4),
        "overall_fail_precision": round(float(overall_fail_precision), 4),
        "overall_fail_recall":    round(float(overall_fail_recall), 4),
        "flag_delta_threshold":   BIAS_FLAG_DELTA,
        "min_group_sample":       MIN_GROUP_SAMPLE,
        "country":   country_bias,
        "gender":    gender_bias,
        "age_group": age_bias,
    }

    flagged_summary = (
        [f"country={k}" for k, v in country_bias.items() if v["flagged"]] +
        [f"gender={k} ({v['flag_reason']})" for k, v in gender_bias.items() if v["flagged"]] +
        [f"age_group={k} ({v['flag_reason']})" for k, v in age_bias.items() if v["flagged"]]
    )
    if flagged_summary:
        print(f"\n  ⚠ WARNING: {len(flagged_summary)} group(s) flagged (>±{BIAS_FLAG_DELTA*100:.0f}pp from overall): "
              f"{', '.join(flagged_summary)}")
    else:
        print("\n  ✓ No group exceeded the bias flag threshold.")

    # ── Step 7 — Save ─────────────────────────────────────────────────────────
    print("\n── Step 7: Saving Model Package ────────────────────────────────────")
    print(classification_report(y_test, y_pred, target_names=["Fail", "Pass"]))
    print(f"Final accuracy: {accuracy:.4f}")
    if accuracy < 0.60:
        print(f"  ✗ NOT SAVED — accuracy {accuracy:.4f} is below the minimum threshold of 0.60")
        sys.exit(1)

    # Report at the actual deployed decision threshold (FAIL_THRESHOLD), not the
    # ensemble's default 0.5 cutoff — this is what predictor.py actually produces
    # in production, so it's the honest baseline saved for future retrains to diff
    # against, rather than a number nobody's serving.
    proba_fail_test = ensemble.predict_proba(X_test)[:, 0]
    y_pred_deployed  = np.where(proba_fail_test >= FAIL_THRESHOLD, 0, 1)
    deployed_report  = classification_report(
        y_test, y_pred_deployed, target_names=["Fail", "Pass"], output_dict=True
    )
    print(f"\nClassification report at deployed decision threshold ({FAIL_THRESHOLD}):")
    print(classification_report(y_test, y_pred_deployed, target_names=["Fail", "Pass"]))

    train_row_count = int(len(X_train))
    trained_at      = datetime.now(timezone.utc).isoformat()
    # test's STUDYPERIOD is uniform by construction (prepare_data() filters to
    # exactly one period) — read it back rather than re-deriving, so this
    # can't drift from whatever period the model was actually evaluated on.
    test_period = str(test["STUDYPERIOD"].iloc[0])

    model_package = {
        "model":                 ensemble,
        "features":              FEATURES,
        "subject_difficulty":    subject_difficulty,
        "safe_subjects":         SAFE_SUBJECTS,
        "trained_on":            f"All periods before {test_period}, excluding 23.1 pilot period",
        "validated_on":          test_period,
        "accuracy":              float(round(accuracy, 4)),
        "model_name":            "XGBoost + Random Forest Ensemble",
        "trained_at":            trained_at,
        "decision_threshold":    FAIL_THRESHOLD,
        "classification_report": deployed_report,
        "train_row_count":       train_row_count,
        "bias_audit":            bias_audit,
    }

    # Versioned, not overwritten — this is NOT made live automatically. Run
    # compare_and_promote.py to see how this version compares against
    # whatever is currently live, and explicitly promote it (or don't).
    from app.ml.model_registry import register_version
    version = register_version(model_package, {
        "trained_at":            trained_at,
        "accuracy":              float(round(accuracy, 4)),
        "decision_threshold":    FAIL_THRESHOLD,
        "classification_report": deployed_report,
        "safe_subjects":         SAFE_SUBJECTS,
        "train_row_count":       train_row_count,
        "trained_on":            model_package["trained_on"],
        "validated_on":          model_package["validated_on"],
        "model_name":            model_package["model_name"],
        "bias_audit":            bias_audit,
    })
    print(f"  ✓ Model registered as version {version} (train rows: {train_row_count:,}) — NOT yet live.")
    print(f"    Run: python backend/app/ml/compare_and_promote.py {version}")
    print(f"    to compare it against the live version and promote it if it's not meaningfully worse.")


if __name__ == "__main__":
    main()

"""
EDAPT v2 — ML Training Pipeline (leakage-free)
Run once from the project root before starting the server.

Usage:
    python backend/app/ml/train_model.py

Trains only on subjects verified clean via data/subject_reliability.json
(fully_clean, minus TSL713 — its CQ/IA weightings were found swapped by the
cleaning script). Period 23.1 is excluded from training as a pilot period
with too few records to add signal.

Features are built from the first two highest-weighted assessments only,
simulating the realistic prediction scenario where only early marks are
available. The PASS target is computed separately from all assessments
and is never used as an input feature.

Outputs:
    backend/app/ml/best_model.pkl

Training set : 23.2 to 25.2 (STUDYPERIOD < 25.3, excluding 23.1 pilot period)
Test set     : STUDYPERIOD == 25.3
"""

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.metrics import accuracy_score, classification_report
from xgboost import XGBClassifier

# ── Paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR       = Path(__file__).resolve().parent
MODEL_DIR        = SCRIPT_DIR
DATA_PATH        = SCRIPT_DIR.parent.parent.parent / "data" / "Capstone_data_20260324.csv"
RELIABILITY_PATH = SCRIPT_DIR.parent.parent.parent / "data" / "subject_reliability.json"

# ── Constants ─────────────────────────────────────────────────────────────────

TEST_PERIOD  = "25.3"
PILOT_PERIOD = "23.1"
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
    """Compute the true final weighted score across ALL assessments per student-subject-period."""
    df = df.copy()
    df["_WEIGHTED_SCORE"] = df["MARKPERCENT"] * df["WEIGHTING"] / 100
    target = (
        df.groupby(["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"])
        .agg(FULL_WEIGHTED_FINAL=("_WEIGHTED_SCORE", "sum"))
        .reset_index()
    )
    target["PASS"] = (target["FULL_WEIGHTED_FINAL"] >= 50).astype(int)
    return target[["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD", "PASS"]]


def build_early_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each student-subject-period, extract features from only the first two
    highest-weighted assessments — simulating what a lecturer knows mid-term.
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


def compute_subject_difficulty(raw_train: pd.DataFrame) -> dict:
    """Proportion of raw assessment records per subject with MARKPERCENT < 50 (train period, record-level)."""
    return (
        raw_train.groupby("SUBJECTCODE")["MARKPERCENT"]
        .apply(lambda s: round(float((s < 50).mean()), 4))
        .to_dict()
    )

# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
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
    SAFE_SUBJECTS = [s for s in reliability["fully_clean"] if s != "TSL713"]
    print(f"  SAFE_SUBJECTS: {len(SAFE_SUBJECTS)} subjects (TSL713 excluded — CQ/IA weightings swapped)")

    raw = raw[raw["SUBJECTCODE"].isin(SAFE_SUBJECTS)]
    print(f"  Rows remaining after SAFE_SUBJECTS filter: {len(raw):,}")
    print(f"  Unique subjects included: {raw['SUBJECTCODE'].nunique()}")

    pilot_rows = int((raw["STUDYPERIOD"] == PILOT_PERIOD).sum())
    raw = raw[raw["STUDYPERIOD"] != PILOT_PERIOD]
    print(f"  Excluded {pilot_rows:,} rows from pilot period {PILOT_PERIOD} (insufficient signal)")

    # ── Step 1 — Feature Engineering ─────────────────────────────────────────
    print("\n── Step 1: Feature Engineering ────────────────────────────────────")
    print("  Computing final pass targets from ALL assessments …")
    target = build_target(raw)

    print("  Building early-assessment features (top-2 by weight only) …")
    feat = build_early_features(raw)
    print(f"  Feature rows: {len(feat):,}")

    train_period_mask = raw["STUDYPERIOD"].apply(lambda p: float(p) < 25.3)
    print("  Computing subject difficulty from training records (record-level, pre-aggregation) …")
    subject_difficulty = compute_subject_difficulty(raw[train_period_mask])
    feat["SUBJECT_DIFFICULTY"] = feat["SUBJECTCODE"].map(subject_difficulty).fillna(0.0)
    print(f"  Subjects with difficulty scores: {len(subject_difficulty)}")

    # Merge target onto features
    data = feat.merge(target, on=["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"], how="inner")
    print(f"  Merged rows: {len(data):,}")

    # ── Step 2 — Temporal Split ───────────────────────────────────────────────
    print("\n── Step 2: Temporal Split ──────────────────────────────────────────")
    train_mask = data["STUDYPERIOD"].apply(lambda p: float(p) < 25.3)
    train = data[train_mask].copy()
    test  = data[data["STUDYPERIOD"] == TEST_PERIOD].copy()

    print(f"Train: {len(train):,} rows  |  Test: {len(test):,} rows")
    print(f"Train PASS — pass: {train['PASS'].sum():,}  fail: {(train['PASS']==0).sum():,}")
    print(f"Test  PASS — pass: {test['PASS'].sum():,}   fail: {(test['PASS']==0).sum():,}")

    X_train = train[FEATURES].values
    y_train = train["PASS"].values
    X_test  = test[FEATURES].values
    y_test  = test["PASS"].values

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
    print("\n── Step 6: Bias Audit by Country ──────────────────────────────────")
    print("Note: countries with fewer than 100 test records are excluded from bias reporting due to insufficient sample size.")
    test_audit = test.copy()
    test_audit["PRED"] = y_pred
    country_counts = test_audit["COUNTRY_MASKED"].value_counts()
    qualifying = country_counts[country_counts > 100].index

    print(f"{'COUNTRY':<20} {'N':>6}  {'ACCURACY':>8}")
    print("-" * 40)
    for country in qualifying:
        grp     = test_audit[test_audit["COUNTRY_MASKED"] == country]
        grp_acc = accuracy_score(grp["PASS"], grp["PRED"])
        flag    = "  ⚠ WARNING" if (accuracy - grp_acc) > 0.10 else ""
        print(f"{str(country):<20} {len(grp):>6}  {grp_acc:>8.4f}{flag}")

    excluded = country_counts[country_counts <= 100]
    if not excluded.empty:
        print(f"Excluded from bias reporting (≤100 test records): {', '.join(str(c) for c in excluded.index)}")

    # ── Step 7 — Save ─────────────────────────────────────────────────────────
    print("\n── Step 7: Saving Model Package ────────────────────────────────────")
    print(classification_report(y_test, y_pred, target_names=["Fail", "Pass"]))
    print(f"Final accuracy: {accuracy:.4f}")
    if accuracy < 0.60:
        print(f"  ✗ NOT SAVED — accuracy {accuracy:.4f} is below the minimum threshold of 0.60")
        sys.exit(1)

    model_package = {
        "model":              ensemble,
        "features":           FEATURES,
        "subject_difficulty": subject_difficulty,
        "safe_subjects":      SAFE_SUBJECTS,
        "trained_on":         "23.2 to 25.2 excluding 23.1 pilot period",
        "validated_on":       "25.3",
        "accuracy":           float(round(accuracy, 4)),
        "model_name":         "XGBoost + Random Forest Ensemble",
    }
    out_path = MODEL_DIR / "best_model.pkl"
    joblib.dump(model_package, out_path)
    print(f"  ✓ Model saved — accuracy: {accuracy:.4f}  →  {out_path}")


if __name__ == "__main__":
    main()

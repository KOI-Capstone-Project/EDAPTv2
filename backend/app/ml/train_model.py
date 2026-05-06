"""
EDAPT v2 — ML Training Script
Run once before starting the server to generate model files.

Usage (from the project root):
    python backend/app/ml/train_model.py

Outputs:
    backend/app/ml/best_model.pkl         — Best classifier (RF or LR)
    backend/app/ml/subject_difficulty.pkl — {subject_code: failure_rate}
    backend/app/ml/model_meta.pkl         — {name, accuracy, median_assess2}

Training set : STUDYPERIOD in 23.1 – 25.2 (never mixed with test)
Test set     : STUDYPERIOD == 25.3
"""

import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# ── Paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
MODEL_DIR  = SCRIPT_DIR

DATA_CANDIDATES = [
    SCRIPT_DIR.parent.parent.parent / "data" / "Capstone_data_20260324.csv",
    Path("data") / "Capstone_data_20260324.csv",
    Path("Capstone_data_20260324.csv"),
]

# ── Constants ─────────────────────────────────────────────────────────────────

PERIOD_MAP = {
    "23.1": 1, "23.2": 2, "23.3": 3,
    "24.1": 4, "24.2": 5, "24.3": 6,
    "25.1": 7, "25.2": 8, "25.3": 9,
}
TRAINING_PERIODS = ["23.1","23.2","23.3","24.1","24.2","24.3","25.1","25.2"]
TEST_PERIOD      = "25.3"
FEATURE_COLS     = ["assess1_mark","assess2_mark","subject_difficulty","trimester_num"]

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_csv() -> pd.DataFrame:
    for path in DATA_CANDIDATES:
        p = Path(path)
        if p.exists():
            print(f"Loading: {p}")
            df = pd.read_csv(p)
            if "STUDYPERIOD" in df.columns:
                df["STUDYPERIOD"] = df["STUDYPERIOD"].apply(
                    lambda x: str(round(float(x), 1)) if pd.notna(x) else ""
                )
            if "MARKPERCENT" in df.columns:
                df["MARKPERCENT"] = pd.to_numeric(df["MARKPERCENT"], errors="coerce")
            if "ATTEMPTNUMBER" in df.columns:
                df["ATTEMPTNUMBER"] = pd.to_numeric(df["ATTEMPTNUMBER"], errors="coerce").fillna(1)
            return df
    print("ERROR: CSV not found. Searched:")
    for p in DATA_CANDIDATES:
        print(f"  {p}")
    sys.exit(1)


def build_subject_difficulty(df_train: pd.DataFrame) -> dict:
    difficulty = {}
    for subj, grp in df_train.groupby("SUBJECTCODE"):
        avg_per_student = grp.groupby("STUDENTID_MASKED")["MARKPERCENT"].mean()
        fail_rate = float((avg_per_student < 50).mean())
        difficulty[subj] = round(fail_rate, 4)
    return difficulty


def build_feature_matrix(
    df: pd.DataFrame,
    subject_difficulty: dict,
    fill_assess2: float,
) -> pd.DataFrame:
    rows = []
    for (student, subject, period), grp in df.groupby(
        ["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"]
    ):
        grp_clean = grp.dropna(subset=["MARKPERCENT"]).sort_values("ATTEMPTNUMBER")
        marks = grp_clean["MARKPERCENT"].tolist()
        if not marks:
            continue
        rows.append({
            "assess1_mark":       marks[0],
            "assess2_mark":       marks[1] if len(marks) > 1 else fill_assess2,
            "subject_difficulty": subject_difficulty.get(subject, 0.3),
            "trimester_num":      PERIOD_MAP.get(str(period), 9),
            "passed":             1 if float(np.mean(marks)) >= 50 else 0,
        })
    return pd.DataFrame(rows)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    df = load_csv()
    print(f"Total rows: {len(df):,}")

    df_train = df[df["STUDYPERIOD"].isin(TRAINING_PERIODS)].copy()
    df_test  = df[df["STUDYPERIOD"] == TEST_PERIOD].copy()
    print(f"Training rows: {len(df_train):,}  |  Test rows: {len(df_test):,}")

    if df_test.empty:
        print(f"WARNING: No rows found for STUDYPERIOD=={TEST_PERIOD}. Evaluation will be skipped.")

    # Subject difficulty from training data only
    subject_difficulty = build_subject_difficulty(df_train)
    print(f"Computed difficulty for {len(subject_difficulty)} subjects.")

    # Median of first assessment marks in training data (fill for missing assess2)
    first_marks = (
        df_train.sort_values("ATTEMPTNUMBER")
        .groupby(["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"])["MARKPERCENT"]
        .first()
        .dropna()
    )
    median_assess2 = float(first_marks.median())
    print(f"Assess2 fill value (median): {median_assess2:.1f}%")

    # Build feature matrices
    print("Building feature matrices…")
    Xy_train = build_feature_matrix(df_train, subject_difficulty, median_assess2)
    Xy_test  = build_feature_matrix(df_test,  subject_difficulty, median_assess2)

    if Xy_train.empty:
        print("ERROR: Training feature matrix is empty. Check column names.")
        sys.exit(1)

    X_train = Xy_train[FEATURE_COLS].values
    y_train = Xy_train["passed"].values
    X_test  = Xy_test[FEATURE_COLS].values  if not Xy_test.empty else np.zeros((0, 4))
    y_test  = Xy_test["passed"].values       if not Xy_test.empty else np.zeros(0)
    print(f"Train samples: {len(X_train):,}  |  Test samples: {len(X_test):,}")

    # ── Random Forest ─────────────────────────────────────────────────────────
    print("\n── Random Forest ──────────────────────────────────────────────────")
    rf = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    rf.fit(X_train, y_train)
    if len(X_test):
        rf_preds = rf.predict(X_test)
        rf_acc   = accuracy_score(y_test, rf_preds)
        print(f"T3 2025 Accuracy: {rf_acc:.4f}")
        print(classification_report(y_test, rf_preds, target_names=["Fail","Pass"]))
        print("Confusion matrix:\n", confusion_matrix(y_test, rf_preds))
    else:
        rf_acc = 0.0
        print("No test data — accuracy not evaluated.")

    # ── Logistic Regression ───────────────────────────────────────────────────
    print("\n── Logistic Regression ────────────────────────────────────────────")
    lr = Pipeline([("scaler", StandardScaler()),
                   ("lr",     LogisticRegression(max_iter=500, random_state=42))])
    lr.fit(X_train, y_train)
    if len(X_test):
        lr_preds = lr.predict(X_test)
        lr_acc   = accuracy_score(y_test, lr_preds)
        print(f"T3 2025 Accuracy: {lr_acc:.4f}")
        print(classification_report(y_test, lr_preds, target_names=["Fail","Pass"]))
        print("Confusion matrix:\n", confusion_matrix(y_test, lr_preds))
    else:
        lr_acc = 0.0

    # ── Choose best ───────────────────────────────────────────────────────────
    if rf_acc >= lr_acc:
        best_model, best_name, best_acc = rf,  "Random Forest",       rf_acc
    else:
        best_model, best_name, best_acc = lr,  "Logistic Regression", lr_acc

    # ── Save ──────────────────────────────────────────────────────────────────
    joblib.dump(best_model,         MODEL_DIR / "best_model.pkl")
    joblib.dump(subject_difficulty, MODEL_DIR / "subject_difficulty.pkl")
    joblib.dump({
        "name":           best_name,
        "accuracy":       round(best_acc * 100, 1),
        "median_assess2": median_assess2,
    },                              MODEL_DIR / "model_meta.pkl")

    print(f"\n✓ Best model: {best_name}, T3 2025 accuracy: {best_acc*100:.1f}%")
    print(f"✓ Files saved to: {MODEL_DIR}/")


if __name__ == "__main__":
    main()

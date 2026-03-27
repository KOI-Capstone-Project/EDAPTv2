"""
EDAPT v2 — ML Predictor (Mode 2)

Pipeline:
  1. Feature engineering  — build a flat feature matrix from Enrollment +
                            Assessment rows up to T2 2025.
  2. Training             — RandomForestClassifier (target accuracy > 75 %).
  3. Inference            — predict_proba for T3 2025 enrolments.
  4. Persistence          — serialise model to disk with joblib; write
                            Prediction rows to PostgreSQL.
"""

import joblib
import pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder

MODEL_DIR = Path(__file__).parent / "saved_models"
MODEL_DIR.mkdir(exist_ok=True)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert raw assessment rows into a per-student feature matrix.

    Expected columns in df:
        student_masked_id, subject_code, assessment_type_code,
        mark_percent, weighting, attempt_number,
        gender_code, age_group, country_masked_id,
        study_period_code (trimester label)

    Returns a DataFrame with one row per student and engineered features.
    """
    # Aggregate mark stats per student
    agg = (
        df.groupby("student_masked_id")
        .agg(
            avg_mark=("mark_percent", "mean"),
            min_mark=("mark_percent", "min"),
            max_mark=("mark_percent", "max"),
            std_mark=("mark_percent", "std"),
            total_assessments=("mark_percent", "count"),
            avg_attempts=("attempt_number", "mean"),
        )
        .reset_index()
    )

    # Merge demographic columns (take first row per student — static attrs)
    demo = df[["student_masked_id", "gender_code", "age_group", "country_masked_id"]].drop_duplicates(
        subset="student_masked_id"
    )
    features = agg.merge(demo, on="student_masked_id", how="left")

    # Encode categoricals
    for col in ["gender_code", "age_group"]:
        le = LabelEncoder()
        features[col] = le.fit_transform(features[col].fillna("Unknown"))

    features["std_mark"] = features["std_mark"].fillna(0)
    return features


def train(df_train: pd.DataFrame, model_version: str = "rf_v1") -> dict:
    """
    Train a RandomForestClassifier and persist to disk.

    df_train must contain a boolean 'passed' column (True = Pass).
    Returns a dict with accuracy and model path.
    """
    features = build_features(df_train)
    X = features.drop(columns=["student_masked_id"])
    y = df_train.groupby("student_masked_id")["passed"].first().reindex(features["student_masked_id"]).values

    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=42)

    clf = RandomForestClassifier(n_estimators=200, max_depth=8, random_state=42, n_jobs=-1)
    clf.fit(X_train, y_train)

    acc = accuracy_score(y_val, clf.predict(X_val))
    model_path = MODEL_DIR / f"{model_version}.joblib"
    joblib.dump(clf, model_path)

    return {"accuracy": round(acc, 4), "model_path": str(model_path)}


def predict(df_infer: pd.DataFrame, model_version: str = "rf_v1") -> pd.DataFrame:
    """
    Load a trained model and return predictions for df_infer.

    Returns a DataFrame with columns:
        student_masked_id, predicted_pass (bool), pass_probability (float)
    """
    model_path = MODEL_DIR / f"{model_version}.joblib"
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}. Run /api/v1/predictions/train first.")

    clf = joblib.load(model_path)
    features = build_features(df_infer)
    X = features.drop(columns=["student_masked_id"])

    proba = clf.predict_proba(X)[:, 1]   # probability of Pass class
    preds = proba >= 0.5

    return pd.DataFrame(
        {
            "student_masked_id": features["student_masked_id"].values,
            "predicted_pass": preds,
            "pass_probability": proba.round(4),
        }
    )

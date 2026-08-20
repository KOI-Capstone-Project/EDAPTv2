"""
EDAPT v2 — Detects whether a new study period has appeared in the raw data
since the live model was last trained/validated. This is the trigger
condition scheduled_retrain.py checks before retraining.

train_model.py's train/validation/test period boundaries are resolved
dynamically (see resolve_periods(): test = the latest STUDYPERIOD actually
present in the raw data, validation = the second-latest, train = everything
before that) — not hardcoded to a fixed period pair. So once this script
detects a new period and scheduled_retrain.py calls train_model.main(),
that retrain automatically picks up the new period as the new test set;
there's no separate constant elsewhere that also needs updating for the
new data to actually be used.

Usage:
    python backend/app/ml/check_new_period.py
"""

import pandas as pd

from app.ml.model_registry import load_registry, get_live_entry
from app.ml.train_model import DATA_PATH


def latest_period_in_data() -> str:
    df = pd.read_csv(DATA_PATH, usecols=["STUDYPERIOD"])
    periods = df["STUDYPERIOD"].dropna().apply(lambda x: round(float(x), 1))
    return str(periods.max())


def new_period_available():
    """Returns (is_new: bool, latest_period_in_data: str, live_validated_on: str | None)."""
    registry = load_registry()
    live = get_live_entry(registry)
    latest = latest_period_in_data()
    if live is None:
        return True, latest, None
    validated_on = live.get("validated_on")
    is_new = validated_on is not None and float(latest) > float(validated_on)
    return is_new, latest, validated_on


if __name__ == "__main__":
    is_new, latest, validated_on = new_period_available()
    print(f"Latest period in raw data: {latest}")
    print(f"Live model validated on:   {validated_on}")
    print(f"New period available:     {is_new}")

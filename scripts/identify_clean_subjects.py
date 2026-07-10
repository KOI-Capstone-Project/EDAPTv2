"""
Identify which subjects are safe for prediction based on assessment weighting completeness.

Reads:  data/Capstone_data_20260324.csv
Writes: data/subject_reliability.json
        data/subject_reliability_report.csv
"""

import json
from pathlib import Path

import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT     = Path(__file__).resolve().parent.parent
DATA_IN  = ROOT / "data" / "Capstone_data_20260324.csv"
OUT_JSON = ROOT / "data" / "subject_reliability.json"
OUT_CSV  = ROOT / "data" / "subject_reliability_report.csv"

# ── Load ──────────────────────────────────────────────────────────────────────

df = pd.read_csv(DATA_IN)
df.columns = [c.strip() for c in df.columns]
df["STUDYPERIOD"] = df["STUDYPERIOD"].apply(
    lambda x: str(round(float(x), 1)) if pd.notna(x) else ""
)

# ── One row per subject-period-assessment-type ────────────────────────────────

deduped = df.drop_duplicates(subset=["SUBJECTCODE", "STUDYPERIOD", "ASSESSMENTTYPECODE"])

# ── Weight sum per subject-period ─────────────────────────────────────────────

weight_sums = (
    deduped
    .groupby(["SUBJECTCODE", "STUDYPERIOD"])["WEIGHTING"]
    .sum()
    .reset_index()
    .rename(columns={"WEIGHTING": "TOTAL_WEIGHT"})
)
weight_sums["IS_CLEAN"] = weight_sums["TOTAL_WEIGHT"] == 100.0

# ── Aggregate to subject level ────────────────────────────────────────────────

subject_stats = (
    weight_sums
    .groupby("SUBJECTCODE")
    .agg(
        TOTAL_PERIODS=("STUDYPERIOD", "count"),
        CLEAN_PERIODS=("IS_CLEAN", "sum"),
    )
    .reset_index()
)
subject_stats["CLEAN_PERCENTAGE"] = (
    subject_stats["CLEAN_PERIODS"] / subject_stats["TOTAL_PERIODS"] * 100
).round(1)

# ── Classify ──────────────────────────────────────────────────────────────────

def classify(pct: float) -> str:
    if pct == 100.0:
        return "FULLY_CLEAN"
    if pct >= 75.0:
        return "MOSTLY_CLEAN"
    return "UNRELIABLE"

def recommendation(cat: str) -> str:
    if cat == "FULLY_CLEAN":
        return "Safe for prediction — no warning required"
    if cat == "MOSTLY_CLEAN":
        return "Safe for prediction — show yellow warning on incomplete periods"
    return "Exclude from prediction or show red warning — insufficient assessment data"

subject_stats["RELIABILITY_CATEGORY"] = subject_stats["CLEAN_PERCENTAGE"].apply(classify)
subject_stats["RECOMMENDATION"]        = subject_stats["RELIABILITY_CATEGORY"].apply(recommendation)

# ── Sort: category order then subject code ────────────────────────────────────

CAT_ORDER = {"FULLY_CLEAN": 0, "MOSTLY_CLEAN": 1, "UNRELIABLE": 2}
subject_stats["_rank"] = subject_stats["RELIABILITY_CATEGORY"].map(CAT_ORDER)
subject_stats = (
    subject_stats
    .sort_values(["_rank", "SUBJECTCODE"])
    .drop(columns=["_rank"])
    .reset_index(drop=True)
)

# ── Split into three groups ───────────────────────────────────────────────────

fully_clean  = sorted(subject_stats[subject_stats["RELIABILITY_CATEGORY"] == "FULLY_CLEAN" ]["SUBJECTCODE"].tolist())
mostly_clean = sorted(subject_stats[subject_stats["RELIABILITY_CATEGORY"] == "MOSTLY_CLEAN"]["SUBJECTCODE"].tolist())
unreliable   = sorted(subject_stats[subject_stats["RELIABILITY_CATEGORY"] == "UNRELIABLE"  ]["SUBJECTCODE"].tolist())

# ── Write JSON ────────────────────────────────────────────────────────────────

reliability = {
    "fully_clean":  fully_clean,
    "mostly_clean": mostly_clean,
    "unreliable":   unreliable,
}
with open(OUT_JSON, "w") as f:
    json.dump(reliability, f, indent=2)

# ── Write CSV ─────────────────────────────────────────────────────────────────

csv_cols = [
    "SUBJECTCODE", "RELIABILITY_CATEGORY", "TOTAL_PERIODS",
    "CLEAN_PERIODS", "CLEAN_PERCENTAGE", "RECOMMENDATION",
]
subject_stats[csv_cols].to_csv(OUT_CSV, index=False)

# ── Console output ────────────────────────────────────────────────────────────

print("=" * 60)
print(f"FULLY CLEAN SUBJECTS ({len(fully_clean)}) — safe for prediction, no warning")
print("=" * 60)
for s in fully_clean:
    row = subject_stats[subject_stats["SUBJECTCODE"] == s].iloc[0]
    print(f"  {s:<12}  {int(row['CLEAN_PERIODS'])}/{int(row['TOTAL_PERIODS'])} periods clean  (100%)")

print()
print("=" * 60)
print(f"MOSTLY CLEAN SUBJECTS ({len(mostly_clean)}) — safe, yellow warning on bad periods")
print("=" * 60)
for s in mostly_clean:
    row = subject_stats[subject_stats["SUBJECTCODE"] == s].iloc[0]
    print(f"  {s:<12}  {int(row['CLEAN_PERIODS'])}/{int(row['TOTAL_PERIODS'])} periods clean  ({row['CLEAN_PERCENTAGE']:.1f}%)")

print()
print("=" * 60)
print(f"UNRELIABLE SUBJECTS ({len(unreliable)}) — exclude or show red warning")
print("=" * 60)
for s in unreliable:
    row = subject_stats[subject_stats["SUBJECTCODE"] == s].iloc[0]
    print(f"  {s:<12}  {int(row['CLEAN_PERIODS'])}/{int(row['TOTAL_PERIODS'])} periods clean  ({row['CLEAN_PERCENTAGE']:.1f}%)")

print()
print(f"Outputs written:")
print(f"  {OUT_JSON}")
print(f"  {OUT_CSV}")

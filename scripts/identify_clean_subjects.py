"""
Identify which subjects are safe for prediction based on per-enrolment
assessment weighting completeness.

An enrolment (one student's final, resit-combined record for one subject in
one study period — collapsed across ATTEMPTNUMBER at the assessment-type
level, see below) is "clean" if its recorded WEIGHTING sums to 99-101
(allowing for rounding). A subject is classified by the share of its
enrolments that are clean, not by whether any single subject-period
aggregate hits 100 exactly — a subject can have thousands of enrolments and
still look "incomplete" under an aggregate check just because of a handful
of rows with a data entry error.

Reads:  data/Capstone_data_20260729.csv
Writes: data/subject_reliability.json
        data/subject_reliability_report.csv
"""

import json
from pathlib import Path

import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT     = Path(__file__).resolve().parent.parent
DATA_IN  = ROOT / "data" / "Capstone_data_20260729.csv"
OUT_JSON = ROOT / "data" / "subject_reliability.json"
OUT_CSV  = ROOT / "data" / "subject_reliability_report.csv"

# Share of an enrolment's WEIGHTING sum that counts as "clean" (allows rounding).
CLEAN_WEIGHT_LOW, CLEAN_WEIGHT_HIGH = 99.0, 101.0

# A subject is UNRELIABLE if fewer than this share of its enrolments are clean.
UNRELIABLE_THRESHOLD_PCT = 90.0

# ── Manual overrides ────────────────────────────────────────────────────────────
# Forces a subject's classification regardless of what the automated per-enrolment
# check computes. Use this only for known data-quality issues that the automated
# check cannot detect by construction (e.g. two components swapping weightings —
# the total is unchanged, so a weighting-SUM check can never see it). Do not use
# this to work around the automated check for issues it *can* see — fix those in
# the source data instead.
MANUAL_OVERRIDES = {
    "TSL713": {
        "category": "UNRELIABLE",
        "note": (
            "CQ and IA assessment weightings were found swapped by an earlier "
            "cleaning script error (30/20 became 20/30 across all study periods). "
            "The per-enrolment weighting-sum check cannot detect this error type, "
            "since a swap between two components doesn't change the total. This "
            "subject requires manual verification from the data owner (are CQ/IA "
            "weightings currently correct in the source system?) before being "
            "treated as reliable again."
        ),
    },
}

# ── Load ──────────────────────────────────────────────────────────────────────

df = pd.read_csv(DATA_IN)
df.columns = [c.strip() for c in df.columns]
df["STUDYPERIOD"] = df["STUDYPERIOD"].apply(
    lambda x: str(round(float(x), 1)) if pd.notna(x) else ""
)

# ── Collapse multi-attempt enrolments (assessment-type level) ─────────────────
# An "ATTEMPTNUMBER == 1 only" filter (the old approach here) silently drops
# any enrolment whose record starts at attempt 2 or later — 9,386 of 78,886
# enrolments (11.9%) in the 20260729 data have no attempt-1 row at all — and
# ignores resit contributions for every other enrolment. Mirrors
# collapse_attempts_to_latest_per_type() in backend/app/ml/train_model.py:
# for each (student, subject, period, assessment type) independently, keep
# only the row(s) from whichever ATTEMPTNUMBER is highest for that type. This
# reduces to "latest attempt only" when a resit replaces every type at once,
# and correctly falls back to an earlier attempt for any type a resit didn't
# touch — kept as an inline duplicate rather than a cross-package import so
# this script stays runnable standalone, outside the backend's environment.
winning_attempt = df.groupby(
    ["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD", "ASSESSMENTTYPECODE"]
)["ATTEMPTNUMBER"].transform("max")
collapsed = df[df["ATTEMPTNUMBER"] == winning_attempt]

# ── Weight sum per enrolment (subject + period + student) ─────────────────────

enrolments = (
    collapsed
    .groupby(["SUBJECTCODE", "STUDYPERIOD", "STUDENTID_MASKED"])["WEIGHTING"]
    .sum()
    .reset_index()
    .rename(columns={"WEIGHTING": "TOTAL_WEIGHT"})
)
enrolments["IS_CLEAN"] = enrolments["TOTAL_WEIGHT"].between(CLEAN_WEIGHT_LOW, CLEAN_WEIGHT_HIGH)

# ── Aggregate to subject level ────────────────────────────────────────────────

subject_stats = (
    enrolments
    .groupby("SUBJECTCODE")
    .agg(
        TOTAL_PERIODS=("STUDENTID_MASKED", "count"),
        CLEAN_PERIODS=("IS_CLEAN", "sum"),
    )
    .reset_index()
)
subject_stats["CLEAN_PERCENTAGE"] = (
    subject_stats["CLEAN_PERIODS"] / subject_stats["TOTAL_PERIODS"] * 100
).round(1)

# ── Classify ──────────────────────────────────────────────────────────────────
# TOTAL_PERIODS/CLEAN_PERIODS now count enrolments, not study periods, but the
# column names are kept so the JSON/CSV output shape (and downstream readers
# of subject_reliability.json) is unchanged.

def classify(pct: float) -> str:
    if pct == 100.0:
        return "FULLY_CLEAN"
    if pct >= UNRELIABLE_THRESHOLD_PCT:
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

# ── Apply manual overrides ──────────────────────────────────────────────────────
# Layered on top of the automated result computed above — the automated logic
# itself is untouched, this just replaces the outcome for specific known cases.

subject_stats["MANUAL_OVERRIDE_NOTE"] = ""
for code, override in MANUAL_OVERRIDES.items():
    mask = subject_stats["SUBJECTCODE"] == code
    if not mask.any():
        continue
    subject_stats.loc[mask, "RELIABILITY_CATEGORY"]  = override["category"]
    subject_stats.loc[mask, "RECOMMENDATION"]         = (
        f"MANUAL OVERRIDE — {recommendation(override['category'])}"
    )
    subject_stats.loc[mask, "MANUAL_OVERRIDE_NOTE"]   = override["note"]

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
    "notes":        {code: o["note"] for code, o in MANUAL_OVERRIDES.items()},
}
with open(OUT_JSON, "w") as f:
    json.dump(reliability, f, indent=2)

# ── Write CSV ─────────────────────────────────────────────────────────────────

csv_cols = [
    "SUBJECTCODE", "RELIABILITY_CATEGORY", "TOTAL_PERIODS",
    "CLEAN_PERIODS", "CLEAN_PERCENTAGE", "RECOMMENDATION", "MANUAL_OVERRIDE_NOTE",
]
subject_stats[csv_cols].to_csv(OUT_CSV, index=False)

# ── Console output ────────────────────────────────────────────────────────────

print("=" * 60)
print(f"FULLY CLEAN SUBJECTS ({len(fully_clean)}) — safe for prediction, no warning")
print("=" * 60)
for s in fully_clean:
    row = subject_stats[subject_stats["SUBJECTCODE"] == s].iloc[0]
    print(f"  {s:<12}  {int(row['CLEAN_PERIODS'])}/{int(row['TOTAL_PERIODS'])} enrolments clean  (100%)")

print()
print("=" * 60)
print(f"MOSTLY CLEAN SUBJECTS ({len(mostly_clean)}) — safe, yellow warning (some enrolments incomplete)")
print("=" * 60)
for s in mostly_clean:
    row = subject_stats[subject_stats["SUBJECTCODE"] == s].iloc[0]
    print(f"  {s:<12}  {int(row['CLEAN_PERIODS'])}/{int(row['TOTAL_PERIODS'])} enrolments clean  ({row['CLEAN_PERCENTAGE']:.1f}%)")

print()
print("=" * 60)
print(f"UNRELIABLE SUBJECTS ({len(unreliable)}) — exclude or show red warning")
print("=" * 60)
for s in unreliable:
    row = subject_stats[subject_stats["SUBJECTCODE"] == s].iloc[0]
    flag = "  [MANUAL OVERRIDE]" if row["MANUAL_OVERRIDE_NOTE"] else ""
    print(f"  {s:<12}  {int(row['CLEAN_PERIODS'])}/{int(row['TOTAL_PERIODS'])} enrolments clean  ({row['CLEAN_PERCENTAGE']:.1f}%){flag}")

if MANUAL_OVERRIDES:
    print()
    print("=" * 60)
    print("MANUAL OVERRIDES APPLIED")
    print("=" * 60)
    for code, override in MANUAL_OVERRIDES.items():
        print(f"  {code} → {override['category']}")
        print(f"    {override['note']}")

print()
print(f"Outputs written:")
print(f"  {OUT_JSON}")
print(f"  {OUT_CSV}")

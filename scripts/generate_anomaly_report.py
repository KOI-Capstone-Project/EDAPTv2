"""
Generate anomaly report for KOI assessment weighting data.

Reads:  data/Capstone_data_20260324.csv
Writes: data/anomaly_report_for_ken.csv
        data/clean_subjects.csv
"""

from pathlib import Path
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT     = Path(__file__).resolve().parent.parent
DATA_IN  = ROOT / "data" / "Capstone_data_20260324.csv"
OUT_ANOM = ROOT / "data" / "anomaly_report_for_ken.csv"
OUT_CLEN = ROOT / "data" / "clean_subjects.csv"

# ── Load ──────────────────────────────────────────────────────────────────────

df = pd.read_csv(DATA_IN)
df.columns = [c.strip() for c in df.columns]
df["STUDYPERIOD"] = df["STUDYPERIOD"].apply(
    lambda x: str(round(float(x), 1)) if pd.notna(x) else ""
)

# ── Deduplicate: one row per subject-period-assessment-type ───────────────────

deduped = df.drop_duplicates(subset=["SUBJECTCODE", "STUDYPERIOD", "ASSESSMENTTYPECODE"])

# ── Weight sums per subject-period ────────────────────────────────────────────

weight_sums = (
    deduped
    .groupby(["SUBJECTCODE", "STUDYPERIOD"])["WEIGHTING"]
    .sum()
    .reset_index()
    .rename(columns={"WEIGHTING": "TOTAL_WEIGHT"})
)

# ── Assessment types present per subject-period ───────────────────────────────

types_present = (
    deduped
    .sort_values("WEIGHTING", ascending=False)
    .groupby(["SUBJECTCODE", "STUDYPERIOD"])["ASSESSMENTTYPECODE"]
    .apply(lambda codes: ", ".join(str(c) for c in codes))
    .reset_index()
    .rename(columns={"ASSESSMENTTYPECODE": "ASSESSMENT_TYPES_PRESENT"})
)

# ── Num assessment types per subject-period (for clean report) ────────────────

num_types = (
    deduped
    .groupby(["SUBJECTCODE", "STUDYPERIOD"])["ASSESSMENTTYPECODE"]
    .count()
    .reset_index()
    .rename(columns={"ASSESSMENTTYPECODE": "NUM_ASSESSMENT_TYPES"})
)

# ── Merge ─────────────────────────────────────────────────────────────────────

combined = weight_sums.merge(types_present, on=["SUBJECTCODE", "STUDYPERIOD"])
combined = combined.merge(num_types, on=["SUBJECTCODE", "STUDYPERIOD"])
combined["GAP"] = (100 - combined["TOTAL_WEIGHT"]).round(1)

# ── Severity ──────────────────────────────────────────────────────────────────

def severity(gap: float) -> str:
    if gap <= 5:
        return "MINOR"
    if gap <= 20:
        return "MODERATE"
    if gap <= 50:
        return "SEVERE"
    return "CRITICAL"

combined["SEVERITY"] = combined["GAP"].apply(severity)

# ── Missing estimate ──────────────────────────────────────────────────────────

def missing_estimate(gap: float) -> str:
    if gap == 5:
        return "likely OQ missing"
    if gap == 10:
        return "likely OQ or small quiz missing"
    if gap >= 20:
        return "major assessment component missing — manual review required"
    return "partial data missing"

combined["ASSESSMENT_TYPES_MISSING_ESTIMATE"] = combined["GAP"].apply(missing_estimate)

# ── Split clean vs anomalous ──────────────────────────────────────────────────

clean     = combined[combined["GAP"] == 0].copy()
anomalous = combined[combined["GAP"] >  0].copy()

# ── Severity sort order ───────────────────────────────────────────────────────

SEVERITY_ORDER = {"CRITICAL": 0, "SEVERE": 1, "MODERATE": 2, "MINOR": 3}
anomalous["_sev_rank"] = anomalous["SEVERITY"].map(SEVERITY_ORDER)
anomalous = (
    anomalous
    .sort_values(["_sev_rank", "GAP"], ascending=[True, False])
    .drop(columns=["_sev_rank"])
    .reset_index(drop=True)
)

# ── Output 1 — anomaly report ─────────────────────────────────────────────────

anom_cols = [
    "SUBJECTCODE", "STUDYPERIOD", "TOTAL_WEIGHT", "GAP",
    "SEVERITY", "ASSESSMENT_TYPES_PRESENT", "ASSESSMENT_TYPES_MISSING_ESTIMATE",
]
anomalous[anom_cols].to_csv(OUT_ANOM, index=False)

# ── Output 2 — clean subjects ─────────────────────────────────────────────────

clean_cols = ["SUBJECTCODE", "STUDYPERIOD", "TOTAL_WEIGHT", "NUM_ASSESSMENT_TYPES"]
clean[clean_cols].sort_values(["SUBJECTCODE", "STUDYPERIOD"]).to_csv(OUT_CLEN, index=False)

# ── Console summary ───────────────────────────────────────────────────────────

total        = len(combined)
n_clean      = len(clean)
n_anom       = len(anomalous)
pct_clean    = 100 * n_clean / total if total else 0
pct_anom     = 100 * n_anom  / total if total else 0

all_subjects = combined["SUBJECTCODE"].unique()
anom_subjs   = anomalous["SUBJECTCODE"].unique()
clean_subjs  = [s for s in all_subjects if s not in anom_subjs]

sev_counts = anomalous["SEVERITY"].value_counts()

print(f"Total subject-period combinations:  {total}")
print(f"Clean combinations (sum to 100):    {n_clean} ({pct_clean:.1f}%)")
print(f"Anomalous combinations:             {n_anom} ({pct_anom:.1f}%)")
print(f"Subjects with ALL periods clean:    {len(clean_subjs)}")
print(f"Subjects with ANY anomalous period: {len(anom_subjs)}")
print(
    f"Severity breakdown:  "
    f"MINOR {sev_counts.get('MINOR', 0)},  "
    f"MODERATE {sev_counts.get('MODERATE', 0)},  "
    f"SEVERE {sev_counts.get('SEVERE', 0)},  "
    f"CRITICAL {sev_counts.get('CRITICAL', 0)}"
)
print(f"\nOutputs written:")
print(f"  {OUT_ANOM}")
print(f"  {OUT_CLEN}")

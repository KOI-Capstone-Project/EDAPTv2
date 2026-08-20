"""
EDAPT v2 — Build per-enrolment attendance features from masked_attendance.csv.

Attendance is recorded per CLASS SESSION (class_no, actv_no, cls_session_no)
— one row per student per session, not per assessment — so it must be
aggregated up to student-subject-period level before it can be joined onto
anything assessment-based. This script does that aggregation and reports a
match rate against the real enrolment population, rather than assuming the
join will land cleanly.

Attendance codes (confirmed via correlation test against real pass/fail
outcomes, correlation = 0.55 — overriding an earlier incorrect definition
that treated "H" as "Holiday"):
    H = Present
    N = Absent, no reason given (unexplained)
    A = Absent, authorized/explained

Filtering applied before aggregation:
    study_period_code in {T1, T2, T3}   (drops IBT2/INT1/INT2 — different
                                          program structure, not part of the
                                          129 capstone subjects' T1/T2/T3
                                          calendar)
    course              in the capstone SUBJECTCODE set (all subjects
                                          present in the current capstone
                                          file — 129 as of 20260729 — not
                                          just the SAFE_SUBJECTS/124 used
                                          for training, since attendance is
                                          a separate, subject-count-agnostic
                                          data source)
    year                in the capstone data's real YEAR range

Joined onto the enrolment-level table produced by
train_model.collapse_attempts_to_latest_per_type() — the same fixed,
resit-aware collapsing used by the training pipeline — not the raw,
row-level assessment data, and not a naive "first attempt only" or "latest
attempt only" enrolment list.

Usage:
    python -m app.ml.build_attendance_features
"""

from pathlib import Path

import pandas as pd

from app.ml.train_model import DATA_PATH, collapse_attempts_to_latest_per_type

# ── Paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR       = Path(__file__).resolve().parent
# Stored gzipped (119MB -> 9MB) — pd.read_csv() handles .gz transparently.
ATTENDANCE_PATH  = SCRIPT_DIR.parent.parent.parent / "data" / "masked_attendance.csv.gz"
# NOT under data/ — that directory is mounted read-only in the backend
# container (./data:/data:ro in docker-compose.yml), by design, to protect
# the source CSVs from being overwritten by a pipeline script. This script
# runs via `docker exec ... python -m app.ml.build_attendance_features`
# like the rest of backend/app/ml/, so its output goes in a location that
# mount actually allows writes to.
OUTPUT_PATH      = SCRIPT_DIR / "attendance_features.csv"

VALID_PERIOD_CODES = {"T1", "T2", "T3"}
PERIOD_CODE_TO_NUM = {"T1": "1", "T2": "2", "T3": "3"}


def build_attendance_features(
    attendance_path: Path = ATTENDANCE_PATH,
    capstone_path: Path = DATA_PATH,
) -> pd.DataFrame:
    """
    Returns a DataFrame with one row per (STUDENTID_MASKED, SUBJECTCODE,
    STUDYPERIOD) enrolment that has any attendance data, with columns:
    TOTAL_SESSIONS, SESSIONS_PRESENT, SESSIONS_UNEXPLAINED_ABSENT,
    SESSIONS_AUTHORIZED_ABSENT, ATTENDANCE_RATE (H), UNEXPLAINED_ABSENCE_RATE
    (N), ABSENCE_RATE (A only — authorized/explained absences specifically,
    NOT N+A combined; the three rates are mutually exclusive and sum to
    1.0, matching the three real attendance_code values H/N/A one-to-one).
    """
    # ── Load ──────────────────────────────────────────────────────────────
    print(f"Loading {attendance_path} …")
    att = pd.read_csv(attendance_path)
    print(f"  Raw attendance rows: {len(att):,}")

    print(f"Loading {capstone_path} for subject/year scope …")
    capstone = pd.read_csv(capstone_path)
    capstone_subjects = set(capstone["SUBJECTCODE"].unique())
    capstone_years = set(capstone["YEAR"].astype(str).unique())
    print(f"  Capstone subjects: {len(capstone_subjects)}  years: {sorted(capstone_years)}")

    # ── Filter ────────────────────────────────────────────────────────────
    before = len(att)
    att["year"] = att["year"].astype(str)
    mask = (
        att["study_period_code"].isin(VALID_PERIOD_CODES)
        & att["course"].isin(capstone_subjects)
        & att["year"].isin(capstone_years)
    )
    att = att[mask].copy()
    dropped = before - len(att)
    print(f"  Rows dropped by filter: {dropped:,} ({dropped / before * 100:.2f}%)")
    print(f"  Rows kept: {len(att):,}")

    # ── Build the join key: year + study_period_code -> STUDYPERIOD ────────
    att["STUDYPERIOD"] = att["year"].str[-2:] + "." + att["study_period_code"].map(PERIOD_CODE_TO_NUM)
    att = att.rename(columns={"course": "SUBJECTCODE"})

    # ── Aggregate to student-subject-period level ────────────────────────
    print("\nAggregating to student-subject-period level …")
    grp = att.groupby(["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"])
    features = grp["attendance_code"].agg(
        TOTAL_SESSIONS="count",
        SESSIONS_PRESENT=lambda s: (s == "H").sum(),
        SESSIONS_UNEXPLAINED_ABSENT=lambda s: (s == "N").sum(),
        SESSIONS_AUTHORIZED_ABSENT=lambda s: (s == "A").sum(),
    ).reset_index()

    features["ATTENDANCE_RATE"]           = features["SESSIONS_PRESENT"]            / features["TOTAL_SESSIONS"]
    features["UNEXPLAINED_ABSENCE_RATE"]  = features["SESSIONS_UNEXPLAINED_ABSENT"] / features["TOTAL_SESSIONS"]
    features["ABSENCE_RATE"]              = features["SESSIONS_AUTHORIZED_ABSENT"]  / features["TOTAL_SESSIONS"]

    print(f"  Attendance-side enrolments (student-subject-period): {len(features):,}")

    # sanity check: H + N + A are mutually exclusive and must sum to 1.0
    rate_sum = (features["ATTENDANCE_RATE"] + features["UNEXPLAINED_ABSENCE_RATE"] + features["ABSENCE_RATE"]).round(6)
    assert (rate_sum == 1.0).all(), "ATTENDANCE_RATE + UNEXPLAINED_ABSENCE_RATE + ABSENCE_RATE != 1.0 for some rows — code mapping is wrong"

    return features


def match_against_enrolments(features: pd.DataFrame, capstone_path: Path = DATA_PATH) -> pd.DataFrame:
    """
    Joins the attendance features onto the real enrolment population — built
    from the SAME collapse_attempts_to_latest_per_type() logic the training
    pipeline uses, not raw row-level assessment data — and reports the match
    rate rather than assuming it.
    """
    print(f"\nLoading {capstone_path} to build the enrolment population …")
    raw = pd.read_csv(capstone_path)
    raw["STUDYPERIOD"] = raw["STUDYPERIOD"].apply(
        lambda x: str(round(float(x), 1)) if pd.notna(x) else ""
    )
    collapsed = collapse_attempts_to_latest_per_type(raw)
    enrolments = (
        collapsed[["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    print(f"  Real enrolments (collapsed, resit-aware): {len(enrolments):,}")

    merged = enrolments.merge(
        features, on=["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"], how="left"
    )
    matched = merged["TOTAL_SESSIONS"].notna().sum()
    match_rate = matched / len(enrolments) * 100
    print(f"  Enrolments with matching attendance data: {matched:,} / {len(enrolments):,} ({match_rate:.2f}%)")

    return merged


def main() -> None:
    features = build_attendance_features()
    merged = match_against_enrolments(features)

    merged.to_csv(OUTPUT_PATH, index=False)
    print(f"\nOutput written: {OUTPUT_PATH}")
    print(f"  Rows: {len(merged):,}  Columns: {list(merged.columns)}")


if __name__ == "__main__":
    main()

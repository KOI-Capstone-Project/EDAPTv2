"""
EDAPT v2 — Three-tier column classification for CSV ingestion (capstone and
attendance), with a persisted store of reviewer decisions so a column
flagged NEW once and reviewed doesn't get re-flagged on every future
upload.

Every column in an uploaded file lands in exactly one of:
    KEEP — part of the locked schema this pipeline actually uses.
    SKIP — a known, explained column this pipeline deliberately ignores
           (reason shown to the reviewer, not just "skipped").
    NEW  — not recognized. Never silently dropped or silently kept —
           flagged for a human decision. Ingestion still proceeds using
           only the KEEP columns; NEW columns are visible, not blocking.

Reviewer decisions on NEW columns ("keep" or "permanently_skip") persist
in column_review_decisions.json (this directory — writable via the
backend bind mount, unlike /data which is read-only in the container).
Not committed to git — this is accumulated runtime state, same treatment
as model_registry.json's contents.
"""

import json
from pathlib import Path
from typing import Literal

SCRIPT_DIR      = Path(__file__).resolve().parent
DECISIONS_PATH  = SCRIPT_DIR / "column_review_decisions.json"

# ── Locked schemas (Step 0) ─────────────────────────────────────────────────

CAPSTONE_KEEP = [
    "ASSESSMENTTYPECODE", "ATTEMPTNUMBER", "ASSESSMENTMARK", "MAXMARK",
    "WEIGHTING", "GENDERCODE", "AGEGROUP", "STUDYPERIOD", "SUBJECTCODE",
    "CLASSGROUP", "MARKPERCENT", "STUDENTID_MASKED", "COUNTRY_MASKED",
]

CAPSTONE_SKIP: dict[str, str] = {
    "DATECREATED": (
        "Batch-import timestamp, not a real per-assessment date (confirmed: "
        "112,120 rows share one exact date; period 25.3 spans 2022-2025, "
        "which is impossible for a genuine assessment date)"
    ),
    "YEAR": "Fully derivable from STUDYPERIOD",
    "STUDYPERIODCODE": "Fully derivable from STUDYPERIOD",
    "STUDYPACKAGEASSESSMENTID": (
        "Only 6 distinct values (1-6) — an assessment sequence position, "
        "not a unique ID despite its name; PROGRESS_PCT already covers "
        "this better"
    ),
}

# ATTENDANCE_KEEP is the 6-column set stated in the build spec. The real
# masked_attendance.csv has 5 more columns (location_code, building, room,
# class_no, actv_no) not in that list and not given a documented skip
# reason — confirmed directly against the real file, not assumed. They are
# NOT added to ATTENDANCE_SKIP here (no stated reason was given for them),
# so on a real upload they correctly land in NEW rather than being silently
# hidden — flagged in the consolidated report, not papered over.
ATTENDANCE_KEEP = [
    "STUDENTID_MASKED", "course", "study_period_code", "year",
    "cls_session_no", "attendance_code",
]

ATTENDANCE_SKIP: dict[str, str] = {}

Kind = Literal["capstone", "attendance"]


def _load_decisions() -> dict:
    if not DECISIONS_PATH.exists():
        return {"capstone": {}, "attendance": {}}
    with open(DECISIONS_PATH) as f:
        return json.load(f)


def _save_decisions(decisions: dict) -> None:
    with open(DECISIONS_PATH, "w") as f:
        json.dump(decisions, f, indent=2)


def record_column_decision(kind: Kind, column: str, decision: Literal["keep", "permanently_skip"]) -> None:
    """Persist a reviewer's keep/permanently_skip call for a NEW column."""
    decisions = _load_decisions()
    decisions.setdefault(kind, {})[column] = decision
    _save_decisions(decisions)


def classify_columns(present_columns, kind: Kind) -> dict:
    """
    Returns {"keep": [...], "skip": [{"column":..., "reason":...}], "new": [...]}.
    present_columns: iterable of column names actually found in the upload.
    """
    keep_list = CAPSTONE_KEEP if kind == "capstone" else ATTENDANCE_KEEP
    skip_dict = CAPSTONE_SKIP if kind == "capstone" else ATTENDANCE_SKIP
    reviewed  = _load_decisions().get(kind, {})

    keep: list[str] = []
    skip: list[dict] = []
    new:  list[str] = []

    for col in present_columns:
        if col in keep_list:
            keep.append(col)
        elif col in skip_dict:
            skip.append({"column": col, "reason": skip_dict[col]})
        elif col in reviewed:
            if reviewed[col] == "keep":
                keep.append(col)
            else:
                skip.append({"column": col, "reason": "Reviewed and marked as permanently skipped"})
        else:
            new.append(col)

    return {"keep": sorted(keep), "skip": skip, "new": sorted(new)}

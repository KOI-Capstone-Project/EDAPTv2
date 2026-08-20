"""
EDAPT v2 — Unit tests for app.ml.incremental_merge.merge_incremental.

Pure-function tests, no DB/app/event loop needed — this is the
correctness-critical piece behind "Incremental Ingestion" in the Data
Ingestion wizard: a wrong redundant/updated/new classification here either
silently drops a real correction or silently resurrects data that should
have been skipped, so every case (new key, exact duplicate, changed value,
NaN-vs-NaN, the new file's own internal duplicate keys) gets its own test
rather than one broad end-to-end check.
"""

import pandas as pd

from app.ml.incremental_merge import merge_incremental

KEY_COLS = ["STUDENT", "SUBJECT", "PERIOD"]


def _row(student, subject, period, mark, note="x"):
    return {"STUDENT": student, "SUBJECT": subject, "PERIOD": period, "MARK": mark, "NOTE": note}


def test_new_key_is_appended():
    existing = pd.DataFrame([_row("S1", "SUBJ1", "25.1", 70)])
    incoming = pd.DataFrame([_row("S2", "SUBJ1", "25.1", 80)])

    merged, stats = merge_incremental(existing, incoming, KEY_COLS)

    assert stats == {"new_rows": 1, "updated_rows": 0, "redundant_rows": 0}
    assert len(merged) == 2
    assert set(merged["STUDENT"]) == {"S1", "S2"}


def test_exact_duplicate_is_skipped_not_duplicated():
    existing = pd.DataFrame([_row("S1", "SUBJ1", "25.1", 70)])
    incoming = pd.DataFrame([_row("S1", "SUBJ1", "25.1", 70)])  # byte-identical

    merged, stats = merge_incremental(existing, incoming, KEY_COLS)

    assert stats == {"new_rows": 0, "updated_rows": 0, "redundant_rows": 1}
    assert len(merged) == 1
    assert merged.iloc[0]["MARK"] == 70


def test_same_key_different_value_is_treated_as_an_update():
    existing = pd.DataFrame([_row("S1", "SUBJ1", "25.1", 70)])
    incoming = pd.DataFrame([_row("S1", "SUBJ1", "25.1", 95)])  # corrected mark

    merged, stats = merge_incremental(existing, incoming, KEY_COLS)

    assert stats == {"new_rows": 0, "updated_rows": 1, "redundant_rows": 0}
    assert len(merged) == 1  # replaced in place, not appended as a second row
    assert merged.iloc[0]["MARK"] == 95, "the corrected value must win, not the stale existing one"


def test_mixed_batch_counts_each_row_independently():
    existing = pd.DataFrame([
        _row("S1", "SUBJ1", "25.1", 70),   # will be an exact duplicate
        _row("S2", "SUBJ1", "25.1", 60),   # will be updated
        _row("S3", "SUBJ1", "25.1", 50),   # untouched by this upload
    ])
    incoming = pd.DataFrame([
        _row("S1", "SUBJ1", "25.1", 70),   # duplicate of existing S1
        _row("S2", "SUBJ1", "25.1", 88),   # correction for S2
        _row("S4", "SUBJ1", "25.1", 40),   # brand new
    ])

    merged, stats = merge_incremental(existing, incoming, KEY_COLS)

    assert stats == {"new_rows": 1, "updated_rows": 1, "redundant_rows": 1}
    assert len(merged) == 4  # S1, S2 (updated), S3 (untouched), S4 (new)
    by_student = merged.set_index("STUDENT")
    assert by_student.loc["S1", "MARK"] == 70
    assert by_student.loc["S2", "MARK"] == 88
    assert by_student.loc["S3", "MARK"] == 50
    assert by_student.loc["S4", "MARK"] == 40


def test_nan_vs_nan_in_a_non_key_column_counts_as_redundant_not_updated():
    existing = pd.DataFrame([_row("S1", "SUBJ1", "25.1", 70, note=None)])
    incoming = pd.DataFrame([_row("S1", "SUBJ1", "25.1", 70, note=None)])

    merged, stats = merge_incremental(existing, incoming, KEY_COLS)

    assert stats == {"new_rows": 0, "updated_rows": 0, "redundant_rows": 1}, (
        "NaN == NaN must be treated as 'unchanged', not as a difference that triggers an update"
    )


def test_incoming_files_own_internal_duplicate_key_keeps_the_last_occurrence():
    existing = pd.DataFrame([_row("S1", "SUBJ1", "25.1", 70)])
    incoming = pd.DataFrame([
        _row("S1", "SUBJ1", "25.1", 91),  # first occurrence in this upload
        _row("S1", "SUBJ1", "25.1", 99),  # second occurrence, same key — should win
    ])

    merged, stats = merge_incremental(existing, incoming, KEY_COLS)

    assert len(merged) == 1
    assert merged.iloc[0]["MARK"] == 99
    assert stats["updated_rows"] == 1
    assert stats["redundant_rows"] == 0


def test_columns_only_present_on_one_side_are_dropped_from_the_result():
    existing = pd.DataFrame([{**_row("S1", "SUBJ1", "25.1", 70), "OLD_ONLY_COL": "legacy"}])
    incoming = pd.DataFrame([{**_row("S2", "SUBJ1", "25.1", 80), "NEW_ONLY_COL": "fresh"}])

    merged, _ = merge_incremental(existing, incoming, KEY_COLS)

    assert "OLD_ONLY_COL" not in merged.columns
    assert "NEW_ONLY_COL" not in merged.columns

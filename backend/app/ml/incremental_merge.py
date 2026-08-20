"""
EDAPT v2 — Generic incremental-merge/dedup helper for re-ingestion.

Used by both capstone and attendance confirm when the admin chooses
"Incremental Ingestion" over "Override Previous Ingestion" in the Data
Ingestion wizard (see DataIngestion.jsx and main.py's _do_capstone_confirm /
_do_attendance_confirm). A new upload's rows are matched against the
already-committed dataset by a natural key — composite columns that
identify "the same record" (e.g. student+subject+period+assessment
type+attempt for capstone; student+subject+period+session for attendance):

  - key not present in the existing data   -> appended as a new row
  - key present, all non-key values equal  -> exact duplicate, SKIPPED
    (counted as "redundant", never applied)
  - key present, some non-key value differs -> treated as a correction:
    the existing row is UPDATED to the new upload's values

Deliberately vectorized (pandas merges + column-wise comparisons), not a
row-by-row Python loop — this runs on re-uploads of files with millions of
rows (attendance), and it already runs inside a background job (see
IngestJob), not blocking a request, but it still needs to finish in a
reasonable time.
"""

import pandas as pd


def merge_incremental(existing_df: pd.DataFrame, new_df: pd.DataFrame, key_cols: list) -> tuple:
    """
    Returns (merged_df, stats) where stats = {"new_rows", "updated_rows", "redundant_rows"}.

    Only columns present in BOTH dataframes are kept in the merged result —
    matches the existing "align to the committed schema" behavior a plain
    override already has.
    """
    common_cols = [c for c in existing_df.columns if c in new_df.columns]
    existing = existing_df[common_cols].reset_index(drop=True)
    incoming = new_df[common_cols].reset_index(drop=True)

    # The new file's own internal duplicate keys: last occurrence wins, same
    # as a plain override would end up reflecting whatever was written last.
    incoming = incoming.drop_duplicates(subset=key_cols, keep="last").reset_index(drop=True)

    compare_cols = [c for c in common_cols if c not in key_cols]
    probe = incoming.merge(existing, on=key_cols, how="left", suffixes=("", "_old"), indicator=True)

    is_match = probe["_merge"] == "both"
    same_mask = pd.Series(True, index=probe.index)
    for c in compare_cols:
        old_c = f"{c}_old"
        same_mask &= (probe[c] == probe[old_c]) | (probe[c].isna() & probe[old_c].isna())

    redundant_mask = is_match & same_mask
    updated_mask   = is_match & ~same_mask
    new_mask       = probe["_merge"] == "left_only"

    stats = {
        "new_rows":       int(new_mask.sum()),
        "updated_rows":   int(updated_mask.sum()),
        "redundant_rows": int(redundant_mask.sum()),
    }

    rows_to_upsert = incoming.loc[(updated_mask | new_mask).values].reset_index(drop=True)

    # Drop the existing rows being superseded by an update via another merge
    # (hash join), not a Python-level key-membership check, so this stays
    # fast at attendance-file scale.
    existing_tagged = existing.merge(
        rows_to_upsert[key_cols].drop_duplicates(), on=key_cols, how="left", indicator="_dup",
    )
    kept_existing = existing_tagged.loc[existing_tagged["_dup"] == "left_only", common_cols].reset_index(drop=True)

    merged_df = pd.concat([kept_existing, rows_to_upsert], ignore_index=True)
    return merged_df, stats

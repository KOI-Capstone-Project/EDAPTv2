"""
EDAPT v2 — Reconcile logged predictions against real outcomes.

Once a student-subject-period enrolment becomes "clean" (fully graded —
the same per-enrolment weighting-sum check used everywhere else in this
project, not a fixed "T3 2025 results are out" assumption), backfill
actual_pass on any prior prediction rows for that enrolment from the real
final grade.

STANDARD PATH: reuses train_model.load_and_filter_raw() (SAFE_SUBJECTS +
per-enrolment dirty-row filter, ATTEMPTNUMBER==1 only) and
train_model.build_target() (FULL_WEIGHTED_FINAL >= 50) exactly as-is — so
"reconciled via the standard path" always means "measured the exact same
way training does." train_model.py, build_target(), and the training
pipeline's clean-enrolment definition are NOT touched by this file — that
attempt-1-only scope is a separate, bigger decision with its own tradeoffs
(deliberately deferred, discussed elsewhere).

RESIT FALLBACK (this file only, does not affect training): a student whose
earliest recorded attempt for a subject+period isn't attempt 1 (e.g. a
resit/repeat) is permanently invisible to the standard path — verified this
happens (32 of 179 real ICT205/25.3 predictions). For predictions that don't
resolve via the standard path, this retries using that student's LATEST
recorded attempt for that subject+period instead, with the identical
clean-weighting check (99-101) and PASS rule (>=50) — just applied to the
latest attempt's rows instead of attempt 1's. Results from this fallback are
tagged reconciled_via_resit=True and never silently merged with standard
reconciliations in a way that hides which method was used.

Usage:
    python -m app.ml.reconcile_predictions
"""

import asyncio
import os
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Prediction
from app.ml.train_model import load_and_filter_raw, build_target, DATA_PATH

DB_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://sangamgurung@localhost:5432/edapt")

# Same tolerance/threshold as the standard path (load_and_filter_raw()'s
# enrolment-clean check and build_target()'s PASS rule) — deliberately kept
# identical so "clean" and "pass" mean the same thing in both paths. Can't
# import these from train_model.py as shared constants without touching that
# file, which this task explicitly rules out, so they're restated here.
# 50 is KOI's real, confirmed grading pass mark (see build_target()'s
# docstring) — not an independent guess.
CLEAN_WEIGHT_LOW, CLEAN_WEIGHT_HIGH = 99.0, 101.0
PASS_THRESHOLD = 50.0


def build_resit_outcomes(pending_keys: set) -> tuple:
    """
    For (student, subject, period) keys that didn't resolve via the standard
    attempt-1 path, retry using each student's LATEST recorded attempt for
    that subject+period.

    Returns (outcomes, has_any_record):
      outcomes       — {key: PASS} only for keys whose latest attempt's
                        weighting sums cleanly (99-101), same standard as
                        attempt-1, just applied to a different attempt number.
      has_any_record — the subset of pending_keys with ANY row at all in the
                        raw data (clean or not), so callers can distinguish
                        "record exists but is dirty" from "no record found at
                        all" among whatever's left unresolved.

    Reads the raw CSV directly rather than going through
    train_model.load_and_filter_raw() (that function's clean check is
    attempt-1-only by design — reusing it here would just reproduce the same
    gap this function exists to work around). Scoped to only the given
    pending_keys, not a full-dataset scan.
    """
    if not pending_keys:
        return {}, set()

    df = pd.read_csv(
        DATA_PATH,
        usecols=["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD", "ATTEMPTNUMBER", "MARKPERCENT", "WEIGHTING"],
    )
    df["STUDYPERIOD"] = df["STUDYPERIOD"].apply(lambda x: str(round(float(x), 1)) if pd.notna(x) else "")
    df["MARKPERCENT"] = pd.to_numeric(df["MARKPERCENT"], errors="coerce")
    df = df.dropna(subset=["MARKPERCENT"])
    df["STUDENTID_MASKED"] = df["STUDENTID_MASKED"].astype(str)

    keys_df = pd.DataFrame(list(pending_keys), columns=["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"])
    df = df.merge(keys_df, on=["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"], how="inner")

    has_any_record = {
        (str(s), subj, per)
        for s, subj, per in df.groupby(["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"]).groups.keys()
    }

    if df.empty:
        return {}, has_any_record

    latest_attempt = df.groupby(["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"])["ATTEMPTNUMBER"].transform("max")
    df_latest = df[df["ATTEMPTNUMBER"] == latest_attempt]

    weight_sums = df_latest.groupby(["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"])["WEIGHTING"].sum()
    clean_keys = weight_sums[weight_sums.between(CLEAN_WEIGHT_LOW, CLEAN_WEIGHT_HIGH)].index

    df_clean = df_latest.set_index(["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"])
    df_clean = df_clean.loc[df_clean.index.isin(clean_keys)].reset_index()
    df_clean["_WEIGHTED_SCORE"] = df_clean["MARKPERCENT"] * df_clean["WEIGHTING"] / 100
    weighted_final = df_clean.groupby(["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"])["_WEIGHTED_SCORE"].sum()

    outcomes = {
        (str(s), subj, per): bool(score >= PASS_THRESHOLD)
        for (s, subj, per), score in weighted_final.items()
    }
    return outcomes, has_any_record


async def reconcile() -> None:
    print("Loading real outcomes — standard path (same clean-enrolment + target logic as training) …")
    raw, _ = load_and_filter_raw()
    target = build_target(raw)
    outcomes = {
        (str(r.STUDENTID_MASKED), r.SUBJECTCODE, r.STUDYPERIOD): bool(r.PASS)
        for r in target.itertuples(index=False)
    }
    print(f"  {len(outcomes):,} clean, fully-graded enrolments available as ground truth (standard path).")

    engine = create_async_engine(DB_URL, echo=False, pool_pre_ping=True)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        result = await db.execute(select(Prediction).where(Prediction.actual_pass.is_(None)))
        pending = result.scalars().all()
        print(f"\n{len(pending):,} prediction row(s) awaiting reconciliation (actual_pass IS NULL).")

        now = datetime.now(timezone.utc)

        # ── Pass 1: standard attempt-1 path ─────────────────────────────────
        backfilled_standard = 0
        still_pending = []
        for pred in pending:
            key = (pred.student_id_masked, pred.subject_code, pred.study_period)
            if key in outcomes:
                await db.execute(
                    update(Prediction)
                    .where(Prediction.id == pred.id)
                    .values(actual_pass=outcomes[key], reconciled_at=now, reconciled_via_resit=False)
                )
                backfilled_standard += 1
            else:
                still_pending.append(pred)

        # ── Pass 2: resit fallback, only for what pass 1 couldn't resolve ───
        pending_keys = {(p.student_id_masked, p.subject_code, p.study_period) for p in still_pending}
        resit_outcomes, has_any_record = build_resit_outcomes(pending_keys)
        print(f"  {len(resit_outcomes):,} additional enrolments resolved via resit fallback "
              f"(latest attempt, same clean-weighting check).")

        backfilled_resit = 0
        residual_dirty = 0
        residual_no_record = 0
        for pred in still_pending:
            key = (pred.student_id_masked, pred.subject_code, pred.study_period)
            if key in resit_outcomes:
                await db.execute(
                    update(Prediction)
                    .where(Prediction.id == pred.id)
                    .values(actual_pass=resit_outcomes[key], reconciled_at=now, reconciled_via_resit=True)
                )
                backfilled_resit += 1
            elif key in has_any_record:
                residual_dirty += 1
            else:
                residual_no_record += 1

        await db.commit()

    total_backfilled = backfilled_standard + backfilled_resit
    print(f"\n  ✓ Backfilled — standard (attempt-1):  {backfilled_standard:,}")
    print(f"  ✓ Backfilled — resit fallback:         {backfilled_resit:,}")
    print(f"    Total backfilled:                    {total_backfilled:,}")
    print(f"\n  Residual — record exists but neither attempt-1 nor latest attempt")
    print(f"             sums cleanly (data-quality gap, not temporal):  {residual_dirty:,}")
    print(f"  Residual — no record at all found for that student+subject+period: {residual_no_record:,}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(reconcile())

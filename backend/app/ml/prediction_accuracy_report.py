"""
EDAPT v2 — Predicted vs. actual accuracy report, computed on REAL outcomes.

This is the number that answers "is the deployed system actually accurate
in practice," not "how did it do on the original 25.3 test set" — it
queries reconciled predictions (predictions.actual_pass populated by
reconcile_predictions.py from real final grades), not the held-out split
train_model.py validates against. The two will often be similar, since
much of what gets reconciled quickly is historical/closed-period data the
model may have partially overlapped with during training — but they are
not the same measurement, and this script never conflates them.

Breaks results out by model_version, so a regression in a specific
deployed version is visible rather than averaged away, and by
estimate_type (complete-record vs. mid-term estimate), since those are
different models with very different expected accuracy (see
train_simulated_progress.py's per-coverage-bin numbers).

Also breaks out by reconciled_via_resit (standard attempt-1 reconciliation
vs. resit-fallback reconciliation — see reconcile_predictions.py). A student
whose outcome was only resolvable via their latest resit attempt may be a
systematically different population (e.g. already flagged as at-risk,
repeating the subject) — this shows whether prediction accuracy actually
differs for that group rather than assuming it doesn't.

Usage (run from backend/, as a module — its imports are package-qualified
so a bare `python backend/app/ml/prediction_accuracy_report.py` no longer
resolves them):
    python -m app.ml.prediction_accuracy_report
"""

import asyncio
import os

from sklearn.metrics import precision_score, recall_score, f1_score, accuracy_score
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Prediction

DB_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://sangamgurung@localhost:5432/edapt")


def _fail_metrics(rows):
    """rows: list of (predicted_pass, actual_pass) bools. Returns dict or None if empty."""
    if not rows:
        return None
    pred_fail = [0 if p else 1 for p, _ in rows]   # 1 = predicted Fail
    true_fail = [0 if a else 1 for _, a in rows]   # 1 = actually failed
    return {
        "n":         len(rows),
        "accuracy":  accuracy_score(true_fail, pred_fail),
        "precision": precision_score(true_fail, pred_fail, zero_division=0),
        "recall":    recall_score(true_fail, pred_fail, zero_division=0),
        "f1":        f1_score(true_fail, pred_fail, zero_division=0),
    }


def _print_metrics(label, m):
    if m is None:
        print(f"  {label}: no reconciled predictions yet")
        return
    print(f"  {label}  (n={m['n']:,})")
    print(f"    accuracy={m['accuracy']:.3f}  Fail precision={m['precision']:.3f}  "
          f"Fail recall={m['recall']:.3f}  Fail f1={m['f1']:.3f}")


async def main() -> None:
    engine = create_async_engine(DB_URL, echo=False, pool_pre_ping=True)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        result = await db.execute(
            select(Prediction).where(Prediction.actual_pass.is_not(None))
        )
        reconciled = result.scalars().all()

    await engine.dispose()

    print("═" * 70)
    print(f"PREDICTED VS. ACTUAL — {len(reconciled):,} reconciled prediction(s)")
    print("═" * 70)
    if not reconciled:
        print("\nNothing reconciled yet. Run reconcile_predictions.py first.")
        return

    overall = [(p.predicted_pass, p.actual_pass) for p in reconciled]
    _print_metrics("OVERALL", _fail_metrics(overall))

    print("\nBy model version:")
    versions = sorted({p.model_version for p in reconciled})
    for v in versions:
        rows = [(p.predicted_pass, p.actual_pass) for p in reconciled if p.model_version == v]
        _print_metrics(v, _fail_metrics(rows))

    print("\nBy estimate type:")
    for label, pred in [
        ("complete-record", lambda p: p.estimate_type is None),
        ("mid-term estimate", lambda p: p.estimate_type == "mid-term estimate"),
    ]:
        rows = [(p.predicted_pass, p.actual_pass) for p in reconciled if pred(p)]
        _print_metrics(label, _fail_metrics(rows))

    print("\nBy reconciliation method:")
    for label, pred in [
        ("standard (attempt-1)", lambda p: not p.reconciled_via_resit),
        ("resit fallback (latest attempt)", lambda p: p.reconciled_via_resit),
    ]:
        rows = [(p.predicted_pass, p.actual_pass) for p in reconciled if pred(p)]
        _print_metrics(label, _fail_metrics(rows))

    standard_m = _fail_metrics([(p.predicted_pass, p.actual_pass) for p in reconciled if not p.reconciled_via_resit])
    resit_m = _fail_metrics([(p.predicted_pass, p.actual_pass) for p in reconciled if p.reconciled_via_resit])
    if standard_m and resit_m:
        acc_delta = resit_m["accuracy"] - standard_m["accuracy"]
        print(f"\n  Resit vs. standard accuracy delta: {acc_delta:+.3f} "
              f"({'meaningfully different' if abs(acc_delta) > 0.10 else 'not meaningfully different'}, "
              f"using the same 10pp threshold style as the bias audit)")


if __name__ == "__main__":
    asyncio.run(main())

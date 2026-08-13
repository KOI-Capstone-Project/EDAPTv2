"""
EDAPT v2 — Did logged interventions coincide with better outcomes?

Compares, among students who received a High Risk prediction that has since
been reconciled to a real outcome (predictions.actual_pass, populated by
reconcile_predictions.py from actual final grades):

    group A — at least one intervention logged AFTER that prediction
    group B — no intervention logged

and reports the actual pass rate of each.

──────────────────────────────────────────────────────────────────────────
READ THIS BEFORE QUOTING ANY NUMBER THIS SCRIPT PRINTS
──────────────────────────────────────────────────────────────────────────
This comparison CANNOT show that interventions work. It is observational,
and the assignment to groups is made by lecturers, not at random. At least
four confounds are live, and none of them are correctable with the data
this project has:

  1. SELECTION ON THE OUTCOME. Lecturers choose who to contact. If they
     intervene on borderline students (the ones most likely to pass anyway),
     group A is biased toward passing and the intervention gets the credit.
     If instead they intervene on the most hopeless cases, group A is biased
     toward failing and a real positive effect is masked. Both are plausible
     and they push in opposite directions, so the sign of the bias is not
     even predictable.
  2. NO CONTROL FOR SEVERITY. "High Risk" is a band, not a point. A student
     at 0.95 predicted-fail and one at 0.66 are both High Risk and have very
     different baseline odds.
  3. LOGGING IS VOLUNTARY. An unlogged intervention (a corridor
     conversation, an email not recorded here) puts a genuinely-helped
     student in the "no intervention" group. Group B is "no intervention
     RECORDED", which is not the same as "no intervention".
  4. NO TIME-TO-OUTCOME CONTROL. An action logged the day before results
     are finalised cannot plausibly have changed anything, but counts the
     same as one logged in week 3.

A difference here is a prompt to design a real evaluation, not evidence of
one. Reported honestly rather than omitted, because the number is genuinely
interesting to a lecturer — it is the interpretation that has to stay
disciplined.

Usage (from backend/):
    python -m app.ml.intervention_outcome_report
"""

import asyncio
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Intervention, Prediction

DB_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://sangamgurung@localhost:5432/edapt")

# Below this, a percentage is noise dressed as a finding. Chosen to match the
# order of magnitude this project already treats as too small to act on
# elsewhere (the 10pp bias-audit flag, the 0.03 threshold noise band).
MIN_GROUP_FOR_A_RATE = 10


async def collect(session: AsyncSession) -> dict:
    """Gather the comparison. Separated from printing so a caller (e.g. the
    model-health endpoint) can reuse the exact same computation rather than
    re-deriving it and drifting."""
    high_risk = (await session.execute(
        select(Prediction).where(
            Prediction.risk_band == "High Risk",
            Prediction.actual_pass.is_not(None),
        )
    )).scalars().all()

    interventions = (await session.execute(select(Intervention))).scalars().all()

    # Index interventions by the enrolment they belong to.
    by_enrolment: dict[tuple, list] = {}
    for iv in interventions:
        by_enrolment.setdefault(
            (iv.student_id_masked, iv.subject_code, iv.study_period), []
        ).append(iv)

    with_iv, without_iv = [], []
    for p in high_risk:
        key = (p.student_id_masked, p.subject_code, p.study_period)
        # AFTER the prediction only: an action logged before the student was
        # ever flagged was not a response to that flag.
        later = [
            iv for iv in by_enrolment.get(key, [])
            if p.predicted_at is None or iv.created_at is None or iv.created_at > p.predicted_at
        ]
        (with_iv if later else without_iv).append(p)

    def rate(rows):
        if not rows:
            return None
        return sum(1 for r in rows if r.actual_pass) / len(rows)

    return {
        "high_risk_reconciled":       len(high_risk),
        "total_interventions_logged": len(interventions),
        "with_intervention":    {"n": len(with_iv),    "pass_rate": rate(with_iv)},
        "without_intervention": {"n": len(without_iv), "pass_rate": rate(without_iv)},
        "sufficient_data": (
            len(with_iv) >= MIN_GROUP_FOR_A_RATE and len(without_iv) >= MIN_GROUP_FOR_A_RATE
        ),
        "min_group_for_a_rate": MIN_GROUP_FOR_A_RATE,
    }


def _fmt(group: dict) -> str:
    if group["n"] == 0:
        return "no students in this group"
    if group["pass_rate"] is None:
        return f"n={group['n']}, pass rate unavailable"
    return f"n={group['n']:,}  actually passed: {group['pass_rate'] * 100:.1f}%"


def render(data: dict) -> str:
    """Format collect()'s output as the human-readable report main() prints.

    Separated from collect() so the refusal logic is testable without a
    database: given thin groups it must print NOT ENOUGH DATA and no
    percentage, and given ample groups it must still print the "not evidence"
    caveat. Both are asserted in the test suite.
    """
    out = []
    out.append("=" * 74)
    out.append("INTERVENTION VS. OUTCOME — High Risk predictions with a real outcome")
    out.append("=" * 74)
    out.append(f"High Risk predictions reconciled to a real outcome: {data['high_risk_reconciled']:,}")
    out.append(f"Interventions logged (all time, all risk bands):    {data['total_interventions_logged']:,}")
    out.append("")
    out.append(f"  intervention logged after the prediction : {_fmt(data['with_intervention'])}")
    out.append(f"  no intervention logged                  : {_fmt(data['without_intervention'])}")
    out.append("")

    a, b = data["with_intervention"], data["without_intervention"]
    if not data["sufficient_data"]:
        out.append(
            f"VERDICT: NOT ENOUGH DATA. Both groups need at least "
            f"{data['min_group_for_a_rate']} students before a percentage means "
            f"anything; this has {a['n']} and {b['n']}."
        )
        out.append(
            "No comparison is reported. A difference computed from these counts "
            "would be arithmetic, not evidence."
        )
    else:
        delta = (a["pass_rate"] - b["pass_rate"]) * 100
        out.append(f"Difference in actual pass rate: {delta:+.1f} percentage points")
        out.append("")
        out.append("THIS IS NOT EVIDENCE THAT INTERVENTIONS WORK. Lecturers choose who")
        out.append("to contact, so the groups differ by more than the intervention — see")
        out.append("this module's docstring for the four live confounds. Treat it as a")
        out.append("prompt to design a real evaluation, not as a result.")
    out.append("=" * 74)
    return "\n".join(out)


async def main() -> None:
    engine = create_async_engine(DB_URL, echo=False, pool_pre_ping=True)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as db:
        data = await collect(db)
    await engine.dispose()
    print(render(data))


if __name__ == "__main__":
    asyncio.run(main())

"""
EDAPT v2 — "what would help most": picking the single most actionable factor
pulling a student toward risk, from the SHAP explanation already computed.

This derives from the REAL SHAP output produced by explain.py — it never
re-scores, re-weights, or invents a number. It answers a narrower question
than SHAP does: not "what drove this prediction" (which includes things
nobody can act on) but "of the things this student could actually change,
which is hurting them most right now".

──────────────────────────────────────────────────────────────────────────
WHY SOME FEATURES ARE EXCLUDED FROM THE RANKING
──────────────────────────────────────────────────────────────────────────
A factor is only worth showing a lecturer if acting on it is possible. Three
distinct reasons a feature is excluded, kept as separate sets because they
are separate arguments — not one lumped "ignore" list:

1. NON_ACTIONABLE_STRUCTURAL — real drivers, but not the student's to change.
   SUBJECT_DIFFICULTY is a property of the subject (its historical fail
   rate). ASSESS1_WEIGHT/ASSESS2_WEIGHT are set by the subject's assessment
   design. TRIMESTER_NUM is the calendar. PARTIAL_WEIGHT_COVERAGE is how
   much of the term has been MARKED — driven by the teaching schedule, not
   by the student. Telling a student to "improve subject difficulty" is
   noise at best and blame-shifting at worst.

2. NON_ACTIONABLE_DEMOGRAPHIC — gender, age group, country.
   IMPORTANT AND EASILY MISREAD: **no demographic feature is in either
   model's feature set.** Verified directly against
   predictor._PACKAGE["features"] and _SIM_PACKAGE["features"] — both are
   the same 11 features, none demographic. These attributes exist in the
   dataset and are used for the FAIRNESS AUDIT (train_model.py Step 6), but
   they are never model inputs, so they cannot appear in a SHAP explanation
   today. This set is therefore a forward-compatible guard, not a live
   filter: if anyone ever adds a demographic feature to the model, it must
   never be surfaced as something a student should "improve". Recommending
   that a student change their age or country is incoherent; recommending
   they change their gender is discriminatory. The guard is deliberately
   substring-based so a renamed variant (GENDER_CODE, AGEGROUP_BUCKET) is
   still caught rather than silently slipping through.

3. DERIVED_DUPLICATES — arithmetic restatements of an actionable feature.
   ASSESS1_CONTRIBUTION is ASSESS1_MARK x ASSESS1_WEIGHT / 100, and
   PARTIAL_WEIGHTED_SCORE is the sum of the contributions. They carry no
   advice the underlying mark doesn't already carry, and leaving them in
   would let one real cause (a low mark) occupy several ranking slots and
   crowd out a genuinely different one (attendance). Excluded so the ranking
   compares distinct causes, not the same cause counted three ways.

What remains actionable: ASSESS1_MARK, ASSESS2_MARK, ATTENDANCE_RATE.
"""

from typing import Optional

NON_ACTIONABLE_STRUCTURAL = {
    "SUBJECT_DIFFICULTY",
    "ASSESS1_WEIGHT",
    "ASSESS2_WEIGHT",
    "TRIMESTER_NUM",
    "PARTIAL_WEIGHT_COVERAGE",
}

# Substring-matched, case-insensitive — see reason 2 above.
NON_ACTIONABLE_DEMOGRAPHIC_SUBSTRINGS = (
    "GENDER",
    "AGEGROUP",
    "AGE_GROUP",
    "COUNTRY",
    "ETHNIC",
    "NATIONALITY",
    "DISABILITY",
)

DERIVED_DUPLICATES = {
    "ASSESS1_CONTRIBUTION",
    "ASSESS2_CONTRIBUTION",
    "PARTIAL_WEIGHTED_SCORE",
}

# Plain-language names + the advice attached to each actionable feature.
# Templates, not Gemini: GEMINI_API_KEY is a placeholder in this environment,
# so a Gemini-only implementation would be untestable here and would degrade
# to "unavailable" in the UI. The wording is deliberately about DIRECTION
# ("the biggest lever"), never a magnitude — see recommend()'s docstring.
_ACTIONABLE_COPY = {
    "ATTENDANCE_RATE": (
        "Attendance",
        "attending more of the remaining classes is the biggest single lever this student has",
    ),
    "ASSESS1_MARK": (
        "First assessment mark",
        "support targeted at assessment performance is the biggest single lever this student has",
    ),
    "ASSESS2_MARK": (
        "Second assessment mark",
        "support targeted at assessment performance is the biggest single lever this student has",
    ),
}


def is_actionable(feature: str) -> bool:
    """True when a student could plausibly influence this feature."""
    name = (feature or "").upper()
    if name in NON_ACTIONABLE_STRUCTURAL or name in DERIVED_DUPLICATES:
        return False
    if any(sub in name for sub in NON_ACTIONABLE_DEMOGRAPHIC_SUBSTRINGS):
        return False
    return name in _ACTIONABLE_COPY


def top_actionable_factor(shap_explanation: Optional[dict]) -> Optional[dict]:
    """The actionable feature with the largest NEGATIVE SHAP contribution.

    Negative only, deliberately. A factor already helping the student (pushing
    toward Pass) is not something to "improve" — surfacing the largest
    magnitude regardless of sign would routinely recommend acting on a
    student's strongest area. Returns None when nothing actionable is
    currently hurting them, which is a real and correct answer.
    """
    if not shap_explanation:
        return None
    factors = shap_explanation.get("all_factors") or []

    harmful = [
        f for f in factors
        if is_actionable(f.get("feature", "")) and f.get("contribution", 0) < 0
    ]
    if not harmful:
        return None

    worst = min(harmful, key=lambda f: f["contribution"])   # most negative
    label, advice = _ACTIONABLE_COPY[worst["feature"].upper()]
    return {
        "feature":      worst["feature"],
        "label":        label,
        "value":        worst["value"],
        "contribution": worst["contribution"],
        "message":      f"{label} is the largest factor pulling this student toward risk — {advice}.",
        # Named so no caller mistakes this for a predicted outcome.
        "basis": (
            "Derived from this prediction's real SHAP contributions. Indicates "
            "direction and relative importance only — not a predicted change in "
            "outcome."
        ),
    }


def excluded_factor_summary(shap_explanation: Optional[dict]) -> list:
    """Factors that were hurting this student but were excluded as not
    actionable. Returned so the UI/tests can show the ranking was a real
    choice rather than silently dropping the biggest driver — a lecturer
    seeing "attendance" should be able to tell that subject difficulty was
    considered and deliberately set aside.
    """
    if not shap_explanation:
        return []
    return [
        {"feature": f["feature"], "contribution": f["contribution"],
         "reason": _exclusion_reason(f["feature"])}
        for f in (shap_explanation.get("all_factors") or [])
        if f.get("contribution", 0) < 0 and not is_actionable(f.get("feature", ""))
    ]


def _exclusion_reason(feature: str) -> str:
    name = (feature or "").upper()
    if any(sub in name for sub in NON_ACTIONABLE_DEMOGRAPHIC_SUBSTRINGS):
        return "demographic — never actionable advice"
    if name in NON_ACTIONABLE_STRUCTURAL:
        return "structural — not the student's to change"
    if name in DERIVED_DUPLICATES:
        return "derived from an actionable feature — would double-count it"
    return "not a recognised actionable feature"

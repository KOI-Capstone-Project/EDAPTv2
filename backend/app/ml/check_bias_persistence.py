"""
EDAPT v2 — Cross-version bias persistence check.

train_model.py's Step 6 bias audit (fail-class precision/recall/F1 broken
out by country, gender, and age_group, flagged if >10pp off the overall
rate) is computed fresh on every retrain and persisted per registry
version. A single flagged group on a single retrain could just be sampling
noise; the same group getting flagged across multiple, independent
retrains is a real signal worth acting on. This script reads bias_audit
across registry history and reports which groups (if any) have been
flagged consistently across consecutive retrains, versus only once.

"Independent" retrain here specifically means a distinct (trained_on,
validated_on) period pair. Re-running train_model.py again without the
underlying data or period changing reproduces a byte-identical bias_audit
— that's not a second data point confirming anything, it's the same
measurement twice. This script deduplicates on period pair before judging
persistence, and says so explicitly rather than treating a re-run as
replication.

Usage (run from backend/, as a module):
    python -m app.ml.check_bias_persistence
"""

from app.ml.model_registry import load_registry

CATEGORIES = ("country", "gender", "age_group")


def _flagged_groups(entry: dict) -> dict:
    """category -> {group_name: flag_reason} for every flagged group in one bias_audit entry."""
    audit = entry["bias_audit"]
    out = {}
    for category in CATEGORIES:
        flagged = {name: g.get("flag_reason") for name, g in audit.get(category, {}).items() if g.get("flagged")}
        if flagged:
            out[category] = flagged
    return out


def _longest_streak(flags: list) -> int:
    best = cur = 0
    for f in flags:
        if f:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _print_single_snapshot(entry: dict) -> None:
    flagged = _flagged_groups(entry)
    if not flagged:
        print("\n  No group was flagged in this audit.")
        return
    for category, groups in flagged.items():
        for name, reason in groups.items():
            print(f"  [{category}] {name}: flagged ({reason or 'see registry for detail'})")


def _print_trend(distinct_points: list) -> None:
    print(f"\n{'=' * 70}")
    print(f"TREND ACROSS {len(distinct_points)} INDEPENDENT RETRAINS (distinct period pairs)")
    print("=" * 70)

    # category -> group name -> [(version, flagged_bool, reason), ...] in chronological order
    history = {}
    for entry in distinct_points:
        audit = entry["bias_audit"]
        for category in CATEGORIES:
            for name, g in audit.get(category, {}).items():
                history.setdefault(category, {}).setdefault(name, []).append(
                    (entry["version"], bool(g.get("flagged")), g.get("flag_reason"))
                )

    any_ever_flagged = False
    for category, groups in history.items():
        for name, records in groups.items():
            flags = [r[1] for r in records]
            if not any(flags):
                continue
            any_ever_flagged = True
            n_flagged, n_total = sum(flags), len(flags)
            streak = _longest_streak(flags)
            currently_flagged = flags[-1]

            if streak >= 2 and currently_flagged:
                verdict = f"flagged in {streak} CONSECUTIVE retrains including the most recent — persistent, not noise"
            elif n_flagged >= 2:
                verdict = f"flagged in {n_flagged}/{n_total} independent retrains, not all consecutive — recurring but intermittent"
            else:
                verdict = f"flagged in only 1/{n_total} independent retrains so far — appears isolated, not (yet) a trend"

            print(f"\n  [{category}] {name}: {verdict}")
            for version, flagged_bool, reason in records:
                mark = "FLAGGED" if flagged_bool else "ok"
                print(f"    {version}: {mark}" + (f" ({reason})" if reason else ""))

    if not any_ever_flagged:
        print("\n  No group was flagged in any of the independent retrains checked.")


def main() -> None:
    registry = load_registry()
    versions = registry.get("versions", [])
    audited = [v for v in versions if "bias_audit" in v]

    print("=" * 70)
    print(f"BIAS PERSISTENCE CHECK — {len(audited)} of {len(versions)} registry version(s) carry a persisted bias_audit")
    print("=" * 70)

    if not audited:
        print("\nNo registry version has bias_audit persisted yet — nothing to check.")
        return

    # Dedupe on (trained_on, validated_on): re-running train_model.py without
    # the underlying data or period changing reproduces an identical audit,
    # and that's not a second, independent confirmation of anything.
    seen_periods = {}
    distinct_points = []
    for v in audited:
        key = (v.get("trained_on"), v.get("validated_on"))
        if key not in seen_periods:
            seen_periods[key] = v
            distinct_points.append(v)

    print(f"\n{len(distinct_points)} of those represent a distinct (trained_on, validated_on) period pair")
    print("(re-runs on the same periods reproduce an identical audit, so they aren't counted as independent evidence):")
    for v in audited:
        key = (v.get("trained_on"), v.get("validated_on"))
        is_first_for_key = seen_periods[key] is v
        note = "" if is_first_for_key else "  <- duplicate of an earlier run on the same periods, not counted"
        print(f"  {v['version']}  validated_on={v.get('validated_on')!r}{note}")

    if len(distinct_points) < 2:
        print(f"\nOnly {len(distinct_points)} distinct period pair has a persisted bias_audit so far.")
        print("That is NOT enough independent retrains to say any group is flagged consistently —")
        print("consistency requires seeing the same group recur across multiple, different retrains.")
        print("Reporting what's flagged in this single audit instead of a trend that doesn't exist yet:")
        _print_single_snapshot(distinct_points[0])
        return

    _print_trend(distinct_points)


if __name__ == "__main__":
    main()

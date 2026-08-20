"""
EDAPT v2 — Compare a trained model version against the live one and
(optionally, explicitly) promote it. Also handles rollback.

Never auto-promotes. Defaults to a dry-run report; only actually changes
the live version with --promote, and refuses to promote a version that's
meaningfully worse than the current live one unless --force is also given.

"Meaningfully worse": fail-class recall drops by more than 3 percentage
points, OR fail-class precision drops by more than 3 percentage points,
relative to the currently live version. This threshold is a judgment
call, not a derived constant — 3pp was chosen because the honest
validation work earlier in this project (validate_threshold.py) found a
2-3pp swing between honestly-validated and test-tuned thresholds on this
same dataset, so treating anything inside that band as "noise" and
anything beyond it as "worse" is consistent with what's already been
measured here, not an arbitrary round number.

Usage:
    python backend/app/ml/compare_and_promote.py --list
    python backend/app/ml/compare_and_promote.py <version>                    # report only
    python backend/app/ml/compare_and_promote.py <version> --promote          # promote if not meaningfully worse
    python backend/app/ml/compare_and_promote.py <version> --promote --force  # promote regardless
    python backend/app/ml/compare_and_promote.py --rollback <version>         # roll back (no comparison gate)
"""

import argparse
import sys

from app.ml.model_registry import load_registry, get_version, get_live_entry, promote

MEANINGFULLY_WORSE_RECALL_DROP    = 0.03
MEANINGFULLY_WORSE_PRECISION_DROP = 0.03


def _fail_metrics(entry):
    report = (entry or {}).get("classification_report") or {}
    fail = report.get("Fail", {})
    return fail.get("precision"), fail.get("recall"), fail.get("f1-score")


def _print_version_summary(label, entry):
    if entry is None:
        print(f"  {label}: (none)")
        return
    p, r, f1 = _fail_metrics(entry)
    print(f"  {label}: version={entry['version']}  trained_at={entry.get('trained_at')}")
    print(f"    train_row_count={entry.get('train_row_count')}  decision_threshold={entry.get('decision_threshold')}")
    print(f"    Fail — precision={p}  recall={r}  f1={f1}")


def compare(candidate_entry: dict, live_entry: dict):
    """Returns (verdict, details). verdict: 'no_baseline' | 'meaningfully_worse' | 'not_meaningfully_worse'."""
    if live_entry is None:
        return "no_baseline", {}
    cp, cr, _ = _fail_metrics(candidate_entry)
    lp, lr, _ = _fail_metrics(live_entry)
    if cp is None or cr is None or lp is None or lr is None:
        return "no_baseline", {}
    precision_delta = cp - lp
    recall_delta    = cr - lr
    meaningfully_worse = (
        recall_delta    < -MEANINGFULLY_WORSE_RECALL_DROP or
        precision_delta < -MEANINGFULLY_WORSE_PRECISION_DROP
    )
    return ("meaningfully_worse" if meaningfully_worse else "not_meaningfully_worse"), {
        "precision_delta": precision_delta,
        "recall_delta":    recall_delta,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("version", nargs="?", help="Version to compare/promote")
    parser.add_argument("--promote", action="store_true", help="Actually promote (default is report-only)")
    parser.add_argument("--force", action="store_true", help="Promote even if meaningfully worse")
    parser.add_argument("--rollback", metavar="VERSION", help="Roll back to an earlier version (no comparison gate)")
    parser.add_argument("--list", action="store_true", help="List all registered versions")
    args = parser.parse_args()

    registry = load_registry()

    if args.list:
        print(f"Live version: {registry.get('live_version')}")
        print(f"\n{len(registry['versions'])} version(s):")
        for v in registry["versions"]:
            marker = "  (LIVE)" if v["version"] == registry.get("live_version") else ""
            p, r, f1 = _fail_metrics(v)
            print(f"  {v['version']}{marker}")
            print(f"    trained_at={v.get('trained_at')}  train_rows={v.get('train_row_count')}  "
                  f"Fail P/R/F1={p}/{r}/{f1}")
        return

    if args.rollback:
        target = get_version(registry, args.rollback)
        if target is None:
            print(f"ERROR: version {args.rollback} not found in registry. Use --list to see available versions.")
            sys.exit(1)
        live = get_live_entry(registry)
        print("═" * 70)
        print("ROLLBACK")
        print("═" * 70)
        _print_version_summary("Currently live", live)
        _print_version_summary("Rolling back to", target)
        promote(args.rollback, reason=f"Manual rollback from {registry.get('live_version')}")
        print(f"\n  ✓ Rolled back — {args.rollback} is now live.")
        return

    if not args.version:
        parser.error("a version is required unless --list or --rollback is given")

    candidate = get_version(registry, args.version)
    if candidate is None:
        print(f"ERROR: version {args.version} not found in registry. Use --list to see available versions.")
        sys.exit(1)
    live = get_live_entry(registry)

    print("═" * 70)
    print("COMPARISON")
    print("═" * 70)
    _print_version_summary("Currently live", live)
    _print_version_summary("Candidate", candidate)

    verdict, details = compare(candidate, live)

    print("\n" + "─" * 70)
    if verdict == "no_baseline":
        print("No live version to compare against (or metrics missing) — nothing to gate on.")
    else:
        print(f"Fail-class precision delta (candidate - live): {details['precision_delta']:+.4f}")
        print(f"Fail-class recall delta    (candidate - live): {details['recall_delta']:+.4f}")
        print(f"'Meaningfully worse' threshold: precision or recall drop > "
              f"{MEANINGFULLY_WORSE_PRECISION_DROP:.2f} ({MEANINGFULLY_WORSE_PRECISION_DROP * 100:.0f}pp)")
        print(f"Verdict: {'MEANINGFULLY WORSE' if verdict == 'meaningfully_worse' else 'not meaningfully worse'}")

    if not args.promote:
        print("\n(Report only — pass --promote to actually change the live version.)")
        return

    if verdict == "meaningfully_worse" and not args.force:
        print("\n  ✗ NOT PROMOTED — candidate is meaningfully worse than live. Re-run with --force to override.")
        sys.exit(1)

    reason = (
        f"Compared against {live['version']}: {verdict}" if live is not None
        else "First version promoted (no prior baseline to compare against)"
    )
    if args.force and verdict == "meaningfully_worse":
        reason += " (forced despite regression)"
    promote(args.version, reason=reason)
    print(f"\n  ✓ Promoted — {args.version} is now live.")


if __name__ == "__main__":
    main()

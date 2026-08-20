"""
EDAPT v2 — Scheduled retraining job.

Intended trigger: the start of each new study period (detected via
check_new_period.py). True scheduling infrastructure (cron, Celery beat,
a workflow scheduler) is NOT set up in this environment — this script is
what such a scheduler would invoke, but nothing currently invokes it
automatically. Run it manually for now, e.g. (from backend/, as a module):

    python -m app.ml.scheduled_retrain           # only retrains if a new period is detected
    python -m app.ml.scheduled_retrain --force    # retrain regardless (manual trigger)

To wire up real scheduling once that infrastructure exists, point any of
these at the command above:
  - cron (host or a dedicated container): a daily line like
        0 6 * * *  cd /path/to/EDAPTv2/backend && venv/bin/python -m app.ml.scheduled_retrain >> /var/log/edapt_retrain.log 2>&1
    is enough — the --force-less default already no-ops on days without a
    new period, so daily is safe to run.
  - a docker-compose service running a sleep-loop, or a CI scheduled
    workflow (GitHub Actions `schedule:` trigger) calling the same command.
This script deliberately does not install or modify any of that itself —
adding a cron entry or an always-on container is an infrastructure change
that should be a deliberate, visible decision, not something a training
script does on its own.

This script only detects + retrains + registers a new version — it NEVER
promotes automatically. See compare_and_promote.py, the only thing that
can make a new version live, and only after an explicit comparison report.

After retraining, also re-runs validate_threshold.py's honest sweep against
whatever the CURRENT validation period resolves to, and reports whether the
optimal fail-class threshold has drifted meaningfully (>3pp — the same
magnitude compare_and_promote.py's regression gate uses) from the
currently-configured FAIL_THRESHOLD. FAIL_THRESHOLD (train_model.py) was
tuned against a specific period pair and isn't automatically re-validated
as dynamic period resolution moves training forward — this is that missing
check. It only ever REPORTS the finding; nothing here changes
FAIL_THRESHOLD, consistent with how model promotion already requires an
explicit human decision rather than auto-deciding.
"""

import argparse

from app.ml.check_new_period import new_period_available
from app.ml import train_model
from app.ml.validate_threshold import run_validation_sweep


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="Retrain even if no new study period was detected")
    args = parser.parse_args()

    is_new, latest, validated_on = new_period_available()
    print(f"Latest period in raw data: {latest}")
    print(f"Live model validated on:   {validated_on}")

    if not is_new and not args.force:
        print("\nNo new study period detected — nothing to do. Use --force to retrain anyway.")
        return

    if is_new:
        print(f"\nNew study period detected ({latest} > {validated_on}) — retraining.")
    else:
        print("\n--force given — retraining regardless of period detection.")

    train_model.main()

    print("\nThis registered a new version — it did NOT promote it.")
    print("Run compare_and_promote.py <version> to review and promote (or not).")

    print("\n" + "═" * 70)
    print("THRESHOLD RE-CHECK — is FAIL_THRESHOLD still valid for the current periods?")
    print("═" * 70)
    sweep = run_validation_sweep(verbose=True)

    print("\n" + "═" * 70)
    print("THRESHOLD RE-CHECK SUMMARY")
    print("═" * 70)
    print(f"  Periods checked:       validate={sweep['val_period']}  test={sweep['test_period']}")
    print(f"  Current FAIL_THRESHOLD: {sweep['current_fail_threshold']:.2f}")
    print(f"  Honestly-validated optimum: {sweep['chosen_threshold']:.2f}  "
          f"(delta {sweep['threshold_delta']:+.2f})")
    if sweep["meaningfully_shifted"]:
        print("  ⚠ MEANINGFULLY SHIFTED (>±0.03) — consider re-running "
              "compare_and_promote.py's reasoning against FAIL_THRESHOLD itself.")
        print("    FAIL_THRESHOLD was NOT changed. This is a report, not an action —")
        print("    updating it is a deliberate, separate human decision, the same way")
        print("    promoting a model version is.")
    else:
        print(f"  ✓ Not meaningfully shifted — FAIL_THRESHOLD={sweep['current_fail_threshold']:.2f} still holds up "
              f"for the current periods.")


if __name__ == "__main__":
    main()

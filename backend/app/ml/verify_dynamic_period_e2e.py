"""
EDAPT v2 — End-to-end verification that "new period detected -> retrain"
actually retrains ON the new period's data, not just that detection fires
in isolation.

Builds a synthetic copy of the real CSV with an extra period ("26.1") —
duplicated from a real, already-clean subject's most recent period, so the
synthetic rows are realistic (valid weightings, real subject codes, real
students) rather than fabricated dummy data — then:
  1. Confirms resolve_periods() on the synthetic data returns
     (val=25.3, test=26.1), i.e. validation = "26.1's predecessor".
  2. Runs check_new_period.new_period_available() against the synthetic
     data and confirms it fires (is_new=True, latest="26.1").
  3. Runs scheduled_retrain's underlying train_model.main() against the
     synthetic data and confirms the registered version's metadata says
     trained_on="...before 26.1..." (i.e. through 25.3) and
     validated_on="26.1" — not the old hardcoded "25.3"/"25.2".
  4. Re-runs compare_and_promote.compare() — the same function
     compare_and_promote.py's dry-run uses — between this synthetic
     candidate and whatever is ACTUALLY live in the real registry, to
     confirm the gated-promotion comparison logic still works correctly
     against a non-hardcoded split.

Full isolation: DATA_PATH and the model registry paths are monkey-patched
to a throwaway temp directory for the duration of this script. The real
data/Capstone_data_20260729.csv and the real registry.json / live model
are never written to — only read once, up front, to fetch the real live
entry for step 4's comparison.

Usage:
    python backend/app/ml/verify_dynamic_period_e2e.py
"""

import shutil
import tempfile
from pathlib import Path

import pandas as pd

from app.ml import train_model, check_new_period, model_registry, compare_and_promote

NEW_PERIOD      = "26.1"
SOURCE_SUBJECT  = "ICT205"  # a real, fully_clean subject — duplicated as the synthetic new-period data


def build_synthetic_csv(out_path: Path) -> str:
    """Duplicate one real subject's latest-period rows as a new period. Returns the real latest period found."""
    df = pd.read_csv(train_model.DATA_PATH)
    df.columns = [c.strip() for c in df.columns]
    period_str = df["STUDYPERIOD"].apply(lambda x: str(round(float(x), 1)) if pd.notna(x) else "")
    real_latest = sorted(period_str.unique(), key=lambda p: float(p) if p else -999)[-1]
    print(f"Real data's latest period: {real_latest}")

    source_rows = df[(period_str == real_latest) & (df["SUBJECTCODE"] == SOURCE_SUBJECT)].copy()
    if source_rows.empty:
        raise RuntimeError(f"No rows found for {SOURCE_SUBJECT}/{real_latest} to duplicate — pick a different SOURCE_SUBJECT.")

    synthetic_rows = source_rows.copy()
    synthetic_rows["STUDYPERIOD"] = float(NEW_PERIOD)
    synthetic = pd.concat([df, synthetic_rows], ignore_index=True)
    synthetic.to_csv(out_path, index=False)
    print(f"Synthetic CSV written: {out_path}  "
          f"({len(synthetic):,} total rows, {len(source_rows):,} synthetic {NEW_PERIOD} rows "
          f"duplicated from real {SOURCE_SUBJECT}/{real_latest})")
    return real_latest


def main() -> None:
    # ── Capture the REAL live entry before touching anything, for step 4 ──────
    real_registry  = model_registry.load_registry()
    real_live_entry = model_registry.get_live_entry(real_registry)
    print("═" * 70)
    print("Real live model (captured before isolation, for the final comparison)")
    print("═" * 70)
    if real_live_entry:
        print(f"  version={real_live_entry['version']}  validated_on={real_live_entry.get('validated_on')}")
    else:
        print("  (none)")

    tmp_dir = Path(tempfile.mkdtemp(prefix="edapt_dynamic_period_verify_"))
    synthetic_csv = tmp_dir / "synthetic_data.csv"
    isolated_models_dir = tmp_dir / "models"

    # ── Full isolation: nothing below touches the real CSV or real registry ───
    original = {
        "train_model.DATA_PATH":        train_model.DATA_PATH,
        "check_new_period.DATA_PATH":   check_new_period.DATA_PATH,
        "model_registry.MODELS_DIR":    model_registry.MODELS_DIR,
        "model_registry.REGISTRY_PATH": model_registry.REGISTRY_PATH,
        "model_registry.LEGACY_PKL_PATH": model_registry.LEGACY_PKL_PATH,
    }
    try:
        real_latest = build_synthetic_csv(synthetic_csv)

        train_model.DATA_PATH             = synthetic_csv
        check_new_period.DATA_PATH        = synthetic_csv
        model_registry.MODELS_DIR         = isolated_models_dir
        model_registry.REGISTRY_PATH      = isolated_models_dir / "registry.json"
        model_registry.LEGACY_PKL_PATH    = tmp_dir / "no_legacy_here.pkl"  # must not exist

        # ── Step 1: resolve_periods() on synthetic data ────────────────────────
        print("\n" + "═" * 70)
        print("STEP 1 — resolve_periods() on synthetic data")
        print("═" * 70)
        raw, _ = train_model.load_and_filter_raw()
        val_period, test_period = train_model.resolve_periods(raw)
        print(f"  val_period={val_period}  test_period={test_period}")
        assert test_period == NEW_PERIOD, f"Expected test_period={NEW_PERIOD}, got {test_period}"
        assert val_period == real_latest, f"Expected val_period={real_latest} (26.1's predecessor), got {val_period}"
        print(f"  ✓ test={test_period} (the new period), val={val_period} ({NEW_PERIOD}'s predecessor)")

        # ── Step 2: check_new_period detection ─────────────────────────────────
        print("\n" + "═" * 70)
        print("STEP 2 — check_new_period.new_period_available()")
        print("═" * 70)
        # No isolated registry exists yet, so this correctly reports is_new=True
        # (no live entry to compare against) — same as a genuinely fresh install.
        is_new, latest, validated_on = check_new_period.new_period_available()
        print(f"  is_new={is_new}  latest={latest}  live validated_on={validated_on}")
        assert is_new is True
        assert latest == NEW_PERIOD

        # ── Step 3: actually retrain against the synthetic data ────────────────
        print("\n" + "═" * 70)
        print("STEP 3 — train_model.main() against synthetic data (via scheduled_retrain's path)")
        print("═" * 70)
        train_model.main()

        isolated_registry = model_registry.load_registry()
        assert len(isolated_registry["versions"]) == 1, "Expected exactly one version in the isolated registry"
        candidate = isolated_registry["versions"][0]
        print(f"\n  Registered candidate: version={candidate['version']}")
        print(f"  trained_on:   {candidate['trained_on']}")
        print(f"  validated_on: {candidate['validated_on']}")
        assert candidate["validated_on"] == NEW_PERIOD, (
            f"Expected validated_on={NEW_PERIOD}, got {candidate['validated_on']}"
        )
        assert NEW_PERIOD in candidate["trained_on"], (
            f"Expected trained_on to reference {NEW_PERIOD} as the boundary, got: {candidate['trained_on']}"
        )
        assert isolated_registry["live_version"] is None, "Candidate must NOT be live — nothing promotes automatically."
        print(f"  ✓ Trained through {val_period} (test={test_period}), NOT the old hardcoded 25.2/25.3 split.")
        print(f"  ✓ Not live — confirmed still gated behind compare_and_promote.py.")

        # ── Step 4: re-run the SAME comparison logic compare_and_promote.py's
        #            dry-run uses, against the REAL live model ────────────────
        print("\n" + "═" * 70)
        print("STEP 4 — compare_and_promote.compare() — synthetic candidate vs. REAL live model")
        print("═" * 70)
        verdict, details = compare_and_promote.compare(candidate, real_live_entry)
        compare_and_promote._print_version_summary("Real live", real_live_entry)
        compare_and_promote._print_version_summary("Synthetic candidate (dynamic split)", candidate)
        print(f"\n  Verdict: {verdict}")
        print(f"  Details: {details}")
        assert verdict in ("no_baseline", "meaningfully_worse", "not_meaningfully_worse")
        print("  ✓ compare() ran without error against a non-hardcoded-split candidate.")

        print("\n" + "═" * 70)
        print("ALL ASSERTIONS PASSED")
        print("═" * 70)
        print("This is not a live promotion — the synthetic candidate only ever existed")
        print(f"in an isolated registry at {isolated_models_dir}, now being deleted.")
        print("The real data file and real registry were never written to.")

    finally:
        train_model.DATA_PATH             = original["train_model.DATA_PATH"]
        check_new_period.DATA_PATH        = original["check_new_period.DATA_PATH"]
        model_registry.MODELS_DIR         = original["model_registry.MODELS_DIR"]
        model_registry.REGISTRY_PATH      = original["model_registry.REGISTRY_PATH"]
        model_registry.LEGACY_PKL_PATH    = original["model_registry.LEGACY_PKL_PATH"]
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()

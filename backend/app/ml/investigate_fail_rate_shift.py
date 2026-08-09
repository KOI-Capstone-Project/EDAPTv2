"""
EDAPT v2 — Investigate the 25.2 -> 25.3 fail-rate jump (6.7% -> 12.0%).

Reuses load_and_filter_raw() and build_target() from train_model.py so this
operates on the exact same SAFE_SUBJECTS + enrolment-clean population that
produced the 6.7%/12.0% figures in validate_threshold.py — not a fresh,
differently-filtered read of the raw CSV.

Usage:
    python backend/app/ml/investigate_fail_rate_shift.py
"""

import pandas as pd

from train_model import load_and_filter_raw, build_target

pd.set_option("display.width", 140)


def main() -> None:
    raw, SAFE_SUBJECTS = load_and_filter_raw()
    target = build_target(raw)  # one row per STUDENTID_MASKED+SUBJECTCODE+STUDYPERIOD, with PASS

    for p in ("25.2", "25.3"):
        n = len(target[target["STUDYPERIOD"] == p])
        fails = (target[target["STUDYPERIOD"] == p]["PASS"] == 0).sum()
        print(f"Period {p}: {n:,} enrolments, {fails:,} fail ({fails/n*100:.1f}%)")

    # ── Per-subject fail rate, both periods side by side ─────────────────────
    print("\n" + "=" * 78)
    print("PER-SUBJECT FAIL RATE — 25.2 vs 25.3")
    print("=" * 78)

    t22 = target[target["STUDYPERIOD"] == "25.2"]
    t23 = target[target["STUDYPERIOD"] == "25.3"]

    def subject_stats(t):
        g = t.groupby("SUBJECTCODE")["PASS"].agg(n="count", fails=lambda s: (s == 0).sum())
        g["fail_pct"] = (g["fails"] / g["n"] * 100).round(1)
        return g

    s22 = subject_stats(t22)
    s23 = subject_stats(t23)

    only_22 = sorted(set(s22.index) - set(s23.index))
    only_23 = sorted(set(s23.index) - set(s22.index))
    both    = sorted(set(s22.index) & set(s23.index))

    print(f"Subjects with enrolments in 25.2: {len(s22)}")
    print(f"Subjects with enrolments in 25.3: {len(s23)}")
    print(f"Subjects in both periods:         {len(both)}")
    print(f"Subjects ONLY in 25.2 (absent from 25.3): {only_22}")
    print(f"Subjects ONLY in 25.3 (absent from 25.2, i.e. new): {only_23}")

    # ── Side-by-side table for subjects present in both periods ─────────────
    print(f"\n{'SUBJECT':<10} {'N_25.2':>7} {'FAIL%_25.2':>11}  {'N_25.3':>7} {'FAIL%_25.3':>11}  {'DELTA':>7}")
    print("-" * 78)
    rows = []
    for code in both:
        n22, f22 = int(s22.loc[code, "n"]), float(s22.loc[code, "fail_pct"])
        n23, f23 = int(s23.loc[code, "n"]), float(s23.loc[code, "fail_pct"])
        delta = round(f23 - f22, 1)
        rows.append((code, n22, f22, n23, f23, delta))
    rows.sort(key=lambda r: -r[3])  # sort by 25.3 enrolment count, biggest subjects first
    for code, n22, f22, n23, f23, delta in rows:
        flag = "  ⚠" if delta >= 10 else ""
        print(f"{code:<10} {n22:>7} {f22:>10.1f}%  {n23:>7} {f23:>10.1f}%  {delta:>+6.1f}{flag}")

    # ── Contribution to the overall jump: weighted by 25.3 enrolment share ──
    print("\n" + "=" * 78)
    print("WHICH SUBJECTS DRIVE THE OVERALL JUMP (weighted by 25.3 volume)")
    print("=" * 78)
    total_23 = s23["n"].sum()
    total_fails_23 = s23["fails"].sum()
    print(f"Overall 25.3 fail rate: {total_fails_23}/{total_23} = {total_fails_23/total_23*100:.1f}%")

    contrib = []
    for code in s23.index:
        n23 = s23.loc[code, "n"]
        f23 = s23.loc[code, "fails"]
        share_of_total_fails = f23 / total_fails_23 * 100
        contrib.append((code, int(n23), int(f23), round(share_of_total_fails, 1)))
    contrib.sort(key=lambda r: -r[2])
    print(f"\n{'SUBJECT':<10} {'N_25.3':>7} {'FAILS_25.3':>11} {'% OF ALL 25.3 FAILS':>20}")
    print("-" * 55)
    cumulative = 0.0
    for code, n23, f23, share in contrib[:20]:
        cumulative += share
        print(f"{code:<10} {n23:>7} {f23:>11} {share:>19.1f}%   (cum {cumulative:.1f}%)")

    # ── Demographic mix shift ────────────────────────────────────────────────
    print("\n" + "=" * 78)
    print("DEMOGRAPHIC / COHORT MIX — enrolment-level (dedup by student+subject+period)")
    print("=" * 78)
    dedup = raw.drop_duplicates(subset=["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"])
    for col in ["GENDERCODE", "AGEGROUP"]:
        print(f"\n{col} distribution:")
        for p in ("25.2", "25.3"):
            vc = dedup[dedup["STUDYPERIOD"] == p][col].value_counts(normalize=True).round(3) * 100
            print(f"  {p}: {dict(vc.round(1))}")

    print("\nTop 10 COUNTRY_MASKED by 25.3 volume:")
    c22 = dedup[dedup["STUDYPERIOD"] == "25.2"]["COUNTRY_MASKED"].value_counts(normalize=True) * 100
    c23 = dedup[dedup["STUDYPERIOD"] == "25.3"]["COUNTRY_MASKED"].value_counts(normalize=True) * 100
    top_countries = c23.head(10).index
    print(f"{'COUNTRY':<15} {'% of 25.2':>10} {'% of 25.3':>10}")
    for c in top_countries:
        print(f"{str(c):<15} {c22.get(c, 0):>9.1f}% {c23.get(c, 0):>9.1f}%")


if __name__ == "__main__":
    main()

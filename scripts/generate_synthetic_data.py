"""
EDAPT v2 — generate a synthetic dataset with the real schema and no real people.

WHY THIS EXISTS
The real extracts (data/Capstone_data_*.csv, data/masked_attendance.csv.gz)
were scrubbed from git history on 2026-08-13 — they hold real pseudonymised
records for 7,926 students and the repository was public. They now live on
disk / in private storage only.

CI still has to run the full backend suite, and that suite exercises the real
serving path: the app loads both files at startup, the roster endpoint assembles
features from them, and several tests need a subject with a complete record and
a student whose own attendance rate differs from their subject average. So CI
needs A dataset — just not THAT dataset. This script writes one that is
structurally identical (same columns, same dtypes, same join keys, same
STUDYPERIOD format) and entirely fabricated.

DELIBERATELY NOT A COPY OR A SAMPLE OF THE REAL DATA. Every value here is
generated from a fixed seed. Sampling even a few real rows would put real
student records back into git, which is the exact thing the scrub removed.

Usage:
    python scripts/generate_synthetic_data.py            # writes into data/
    python scripts/generate_synthetic_data.py --out DIR  # elsewhere

CI runs this before the tests (see .github/workflows/ci.yml). Locally it is not
needed — the real files are already on disk and are gitignored.
"""

import argparse
import gzip
import random
from pathlib import Path

# Fixed seed: CI must be deterministic, so a test that passes today cannot fail
# tomorrow because the generated data happened to come out differently.
SEED = 20260813

# Subjects the test suite names explicitly. They must exist here AND must be
# non-"unreliable" in data/subject_reliability.json, or /api/predict short-
# circuits with prediction_available: false before reaching the model.
# Every subject any test names must appear here. A subject that is missing has
# no attendance rows, so _resolve_attendance_rate() finds neither a per-student
# value nor a subject average, the model is called without a required feature,
# and /api/predict returns 503 — which is how ICT101 was caught being absent.
SUBJECTS = ["ICT205", "ACC705", "ICT104", "ICT101", "ICT201", "ICT301"]
PERIODS = ["23.2", "24.1", "24.2", "25.1", "25.2", "25.3"]

# Three assessment types summing to exactly 100% weighting, so every enrolment
# is a "complete record" and routes to the complete-record model. The mid-term
# tier is reached in tests via ?simulate_progress=, not via partial data.
ASSESSMENTS = [("ME", 20.0), ("DA", 30.0), ("FE", 50.0)]

CAPSTONE_COLUMNS = [
    "STUDYPACKAGEASSESSMENTID", "ASSESSMENTTYPECODE", "ATTEMPTNUMBER",
    "ASSESSMENTMARK", "MAXMARK", "WEIGHTING", "YEAR", "STUDYPERIODCODE",
    "GENDERCODE", "DATECREATED", "AGEGROUP", "STUDYPERIOD", "SUBJECTCODE",
    "CLASSGROUP", "MARKPERCENT", "STUDENTID_MASKED", "COUNTRY_MASKED",
]

ATTENDANCE_COLUMNS = [
    "course", "location_code", "building", "room", "study_period_code",
    "year", "class_no", "actv_no", "cls_session_no", "attendance_code",
    "STUDENTID_MASKED",
]

PERIOD_NUM_TO_CODE = {"1": "T1", "2": "T2", "3": "T3"}
GENDERS = ["M", "F"]
AGE_GROUPS = ["0~20", "21~25", "26~30", "31~40"]
BUILDINGS = [("NC", "DARBY", "D101"), ("NC", "KENT", "K204"), ("SC", "ONL", "ONLINE")]


def generate(out_dir: Path, n_students: int = 60) -> tuple[Path, Path]:
    rng = random.Random(SEED)
    out_dir.mkdir(parents=True, exist_ok=True)

    capstone_rows = []
    attendance_rows = []
    row_id = 1

    for subject in SUBJECTS:
        for period in PERIODS:
            year = "20" + period.split(".")[0]
            period_code = PERIOD_NUM_TO_CODE[period.split(".")[1]]

            for i in range(n_students):
                student = f"SynthStudent{i}"
                gender = rng.choice(GENDERS)
                age = rng.choice(AGE_GROUPS)
                country = f"Country{rng.randint(0, 9)}"
                classgroup = f"{subject}-{period}-A"

                # Spread ability so the cohort contains genuine passes AND
                # genuine fails — a dataset where everyone passes would let a
                # broken model still satisfy the roster tests.
                ability = rng.gauss(62, 18)

                for assess_type, weighting in ASSESSMENTS:
                    mark_pct = max(0.0, min(100.0, ability + rng.gauss(0, 8)))
                    max_mark = 100.0
                    capstone_rows.append([
                        row_id, assess_type, 1,
                        round(mark_pct, 2), max_mark, weighting,
                        year, period_code, gender, f"{year}-01-15",
                        age, period, subject, classgroup,
                        round(mark_pct, 2), student, country,
                    ])
                    row_id += 1

                # Attendance: one row per session. The rate is correlated with
                # ability but noisy, so ATTENDANCE_RATE carries real signal
                # without being a perfect proxy for the outcome (which would
                # make it trivially predictive and hide a broken feature path).
                base_rate = min(0.98, max(0.25, ability / 100 + rng.gauss(0, 0.12)))
                loc, building, room = rng.choice(BUILDINGS)
                n_sessions = 13
                for session in range(1, n_sessions + 1):
                    code = "H" if rng.random() < base_rate else rng.choice(["N", "A"])
                    attendance_rows.append([
                        subject, loc, building, room, period_code, year,
                        1, 1, session, code, student,
                    ])

    capstone_path = out_dir / "Capstone_data_20260729.csv"
    with open(capstone_path, "w", encoding="utf-8") as f:
        f.write(",".join(CAPSTONE_COLUMNS) + "\n")
        for r in capstone_rows:
            f.write(",".join(str(x) for x in r) + "\n")

    # Written gzipped at exactly the path the app expects, because
    # main.py/_ATTENDANCE_PATH points at masked_attendance.csv.gz and
    # pd.read_csv decompresses .gz transparently.
    attendance_path = out_dir / "masked_attendance.csv.gz"
    with gzip.open(attendance_path, "wt", encoding="utf-8") as f:
        f.write(",".join(ATTENDANCE_COLUMNS) + "\n")
        for r in attendance_rows:
            f.write(",".join(str(x) for x in r) + "\n")

    print(f"synthetic capstone   : {capstone_path}  ({len(capstone_rows):,} rows)")
    print(f"synthetic attendance : {attendance_path}  ({len(attendance_rows):,} rows)")
    print(f"students: {n_students} x subjects: {len(SUBJECTS)} x periods: {len(PERIODS)}")
    print("NOTE: entirely fabricated from a fixed seed — contains no real student.")
    return capstone_path, attendance_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "data"))
    ap.add_argument("--students", type=int, default=60)
    args = ap.parse_args()
    generate(Path(args.out), args.students)

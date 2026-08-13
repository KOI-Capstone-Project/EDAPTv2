# EDAPT v2 — Educational Data Analytics and Predictive Tool

[![CI](https://github.com/KOI-Capstone-Project/EDAPTv2/actions/workflows/ci.yml/badge.svg?branch=ml_model)](https://github.com/KOI-Capstone-Project/EDAPTv2/actions/workflows/ci.yml)

> King's Own Institute (KOI) — Capstone Project (Second Year)

EDAPT v2 is a role-based academic analytics platform. It predicts whether a student will pass or fail a subject from their recorded assessment marks — both once a subject is complete and, separately, from genuinely mid-semester partial records — and surfaces those predictions, along with real per-feature explanations, through role-scoped dashboards, an assessment-record explorer, and a roster-first predictor tool.

> **Note on repository state**: this README describes what is in the working tree right now, on branch **`ml_model`** — committed and pushed to `origin/ml_model`. A substantial amount of what's documented below — the data-reliability fix, current ML pipeline, automated retraining infrastructure, outcome reconciliation, fairness auditing, SHAP explainability, and the frontend page merges — is **not yet merged to `main`** (`origin/main` is 10 commits behind `ml_model`). If you're reading this from `main`, expect an older version of the system. `sangam_dev` is an earlier development branch and is **not** where this work lives.

---

## Tech Stack

| Layer       | Technology                                                         |
|-------------|---------------------------------------------------------------------|
| Backend     | Python 3.12 · FastAPI · Uvicorn (dev) / Gunicorn + Uvicorn workers (prod) |
| Database    | PostgreSQL 16 · SQLAlchemy 2.0 (async) · asyncpg                    |
| Data / ML   | Pandas · Scikit-Learn · XGBoost · Imbalanced-learn (SMOTE) · SHAP · Joblib · NumPy |
| AI          | Google Gemini API (Flash + Pro models)                              |
| Auth        | JWT (python-jose) · Bcrypt (passlib)                                 |
| Frontend    | React 18 · React Router v6 · Recharts · Axios                       |
| Styling     | Inline styles (no CSS framework)                                    |
| Infra       | Docker Compose (dev + prod) · nginx (prod reverse proxy)             |

A PostgreSQL-backed relational schema now exists and is genuinely used for **users, audit logs, and predictions** (see [Database](#database) below). Student assessment records themselves are still loaded from a CSV into an in-memory pandas DataFrame at startup — not into SQL tables — which is why several tables in the schema (`students`, `subjects`, `enrollments`, `assessments`) exist but stay empty; nothing in the app writes to them. This is a deliberate, documented design choice, not an oversight — see [Database](#database).

---

## Roles

Confirmed directly against `backend/app/main.py`'s role checks and the seeded default accounts. There are **three roles**, plus one orthogonal super-admin flag:

| Role                 | Access                                                                 |
|-----------------------|-------------------------------------------------------------------------|
| `Lecturer`            | Their assigned subjects only — dashboard, explorer, predictor, settings |
| `Head of School`      | Institution-wide analytics, same scope as Head of Technology except audit log / user management |
| `Head of Technology`  | Institution-wide analytics, data ingestion, predictive reports, all subjects |
| `is_super_admin` flag | Independent of role — grants Audit Log and User Management access. Seeded only on the default `admin` account (a Head of Technology) |

`Head of Technology` and `Head of School` are treated identically almost everywhere in the codebase (`user.get("role") in {"Head of Technology", "Head of School"}` appears throughout `main.py`) — the meaningful three-way split for most endpoints is really "Lecturer vs. everyone else," with the super-admin flag layered on top for two specific pages.

---

## Pages & Routes

Verified directly against `frontend/src/App.js` and the current contents of `frontend/src/pages/`.

### Merged (single component, role passed as a prop)

| Page | File | Route(s) | Differentiator |
|------|------|----------|-----------------|
| Predictor | `PredictorView.jsx` | `/predictor` (Lecturer) · `/predictive-reports` (Admin) | `isAdmin` prop — subject scope (all vs. assigned) and page title only |
| Explorer | `ExplorerView.jsx` | `/explorer` (Lecturer) · `/student-analytics` (Admin) | `isLecturer` prop — admin gets an institution-wide subject picker, demographic filters, and a Country column the lecturer view doesn't |
| Settings | `SettingsView.jsx` | `/settings` (both) | `isLecturer` prop, derived from the logged-in user's role — lecturer view adds an Assigned Subjects chip list and a Default Subject on Login preference |

### Still separate, deliberately not merged

| Page | File | Route |
|------|------|-------|
| Lecturer Dashboard | `LecturerDashboard.jsx` | `/dashboard/lecturer` |
| Admin Dashboard | `AdminDashboard.jsx` | `/dashboard/admin` |

The two dashboards were measured, not assumed, before deciding: roughly **23% line-level overlap**, vs. 76–99% for the pairs that were merged — different chart sets and helper components on each side. Merging them would have glued two largely-disjoint render paths together behind a prop flag rather than produced real consolidation.

### Admin-only pages

| Page | File | Route | Gate |
|------|------|-------|------|
| Subject Analytics | `SubjectAnalytics.jsx` | `/subject-analytics` | Head of Technology or Head of School |
| Data Ingestion | `DataIngestion.jsx` | `/data-ingestion` | Head of Technology or Head of School |
| Audit Log | `AuditLog.jsx` | `/audit-log` | `is_super_admin` only |
| User Management | `UserManagement.jsx` | `/users` | `is_super_admin` only |

### Auth pages

| Page | File | Route |
|------|------|-------|
| Login | `Login.jsx` | `/login` |
| Forgot Password | `ForgotPassword.jsx` | `/forgot-password` |

---

## Project Structure

```
EDAPTv2/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app — all routes, auth, ML wiring, Gemini
│   │   ├── db/
│   │   │   └── models.py              # SQLAlchemy models (see Database section)
│   │   └── ml/
│   │       ├── train_model.py                  # Main training pipeline (complete-record model)
│   │       ├── train_simulated_progress.py     # Simulated multi-snapshot partial-progress model
│   │       ├── predictor.py                    # Inference — predict() and predict_partial()
│   │       ├── explain.py                       # SHAP per-feature attribution
│   │       ├── build_shap_background.py         # Caches SHAP background samples to disk
│   │       ├── model_registry.py                # Versioned model registry + concurrency lock
│   │       ├── compare_and_promote.py           # Gated promotion / rollback CLI
│   │       ├── check_new_period.py              # New-study-period detection
│   │       ├── scheduled_retrain.py             # Manual/scheduled retrain entry point
│   │       ├── validate_threshold.py            # Honest, validation-split threshold selection
│   │       ├── reconcile_predictions.py         # Backfills actual_pass against real outcomes
│   │       ├── prediction_accuracy_report.py    # Predicted-vs-actual accuracy report
│   │       ├── check_bias_persistence.py        # Cross-retrain fairness-flag trend detection
│   │       ├── verify_dynamic_period_e2e.py     # Isolated end-to-end test of dynamic period resolution
│   │       ├── investigate_fail_rate_shift.py   # Diagnostic: period-over-period fail-rate investigation
│   │       ├── sim_model_registry.py             # Versioned registry for the mid-term model family
│   │       ├── compare_and_promote_simulated.py  # Gated promotion / rollback CLI (mid-term)
│   │       ├── models/                           # Complete-record model family
│   │       │   ├── registry.json                # Version metadata, live pointer, promotion history
│   │       │   └── model_<timestamp>.pkl         # One file per registered version
│   │       └── models_simulated/                 # Mid-term model family (same layout)
│   │           ├── registry.json
│   │           └── model_<timestamp>.pkl
│   ├── scripts/
│   │   └── retrain_loop.sh            # Sidecar scheduler loop (scheduled_retrain.py → sleep 24h → repeat)
│   ├── tests/
│   │   ├── test_smoke.py              # 15 tests
│   │   └── test_ingestion_e2e.py      # 8 tests (23 total)
│   ├── Dockerfile.dev
│   └── Dockerfile.prod
├── frontend/
│   └── src/
│       ├── App.js                     # Routes + role guards
│       ├── components/
│       │   ├── Layout.jsx
│       │   ├── Sidebar.jsx
│       │   ├── GeminiPanel.jsx
│       │   └── ErrorBoundary.jsx
│       ├── pages/                     # See Pages & Routes above
│       ├── services/api.js            # Axios instance with JWT interceptor
│       └── utils/auth.js
├── data/
│   ├── Capstone_data_20260729.csv     # Raw source data (live — older snapshots in archive/)
│   ├── masked_attendance.csv.gz       # Raw attendance source data (gzipped: 119MB → 9MB; pandas reads .gz directly)
│   ├── subject_reliability.json       # fully_clean / mostly_clean / unreliable classification
│   ├── subject_reliability_report.csv # Human-readable companion to subject_reliability.json
│   └── archive/                       # Superseded raw-data snapshots, kept for before/after comparison
├── scripts/
│   └── identify_clean_subjects.py     # Regenerates subject_reliability.json
├── model_card.md                      # Model identity, training data, ablation results, calibration, limitations
├── docker-compose.yml                 # Dev — db · backend · frontend · pgadmin · scheduler (opt-in)
├── docker-compose.prod.yml            # Prod — db · backend (gunicorn) · scheduler · frontend · nginx
└── nginx/
```

---

## Quick Start (Docker)

Docker Compose is the primary, actually-used way to run this project — confirmed against the current dev workflow.

### Prerequisites

- Docker and Docker Compose
- A `.env` file in the project root — copy `.env.example` to `.env` and fill in real values (see [Environment Variables](#environment-variables) below for what each one does)

### Install the pre-commit hooks — do this before your first commit

This is a required setup step, not an optional extra. The hooks are what stop a lint error, a leftover conflict marker, a private key, or an oversized file reaching the repository, and they run in about a second.

```bash
pip install pre-commit
pre-commit install          # writes .git/hooks/pre-commit — per clone, not per machine
```

`pre-commit install` is per-clone: a fresh `git clone` has no hooks until you run it again. To check the whole tree rather than just staged files (useful the first time):

```bash
pre-commit run --all-files
```

The full test suite is deliberately **not** in these hooks — it takes ~3.5 minutes and needs a running Postgres, which would just train everyone to use `git commit --no-verify`. Running the suite is CI's job; see [CI and quality gates](#ci-and-quality-gates--automating-what-used-to-depend-on-remembering).

### Start everything

```bash
docker compose up --build
```

This starts four services: `db` (Postgres 16), `backend` (FastAPI, hot-reload via a bind mount), `frontend` (React dev server), and `pgadmin`.

| Service | URL |
|---|---|
| Frontend | `http://localhost:3000` |
| Backend API | `http://localhost:8000` |
| API docs (Swagger) | `http://localhost:8000/docs` |
| pgAdmin | `http://localhost:5050` |
| Postgres (direct access) | `localhost:5432` |

### Also starting the retrain scheduler (optional)

The scheduler sidecar is opt-in in dev, gated behind a Compose profile so a plain `docker compose up` doesn't add an extra long-running container:

```bash
docker compose --profile scheduler up --build
```

### Running scripts inside the backend container

ML scripts must be run with the container's environment (correct `DATABASE_URL`, correct Python packages) — running them via a host virtualenv connects to a different, stale local Postgres if one happens to be running. Always:

```bash
docker exec edaptv2_backend python3 -m app.ml.<script_name>
```

---

## Environment Variables

Confirmed against the current `.env` (values redacted; variable names are real):

```bash
# ── PostgreSQL ──────────────────────────────────────────────
POSTGRES_USER=
POSTGRES_PASSWORD=
POSTGRES_DB=
POSTGRES_HOST=
POSTGRES_PORT=

DATABASE_URL=

# ── FastAPI ─────────────────────────────────────────────────
SECRET_KEY=
ENVIRONMENT=
LOG_LEVEL=

# ── pgAdmin ─────────────────────────────────────────────────
PGADMIN_DEFAULT_EMAIL=
PGADMIN_DEFAULT_PASSWORD=

# ── Google Gemini ───────────────────────────────────────────
GEMINI_API_KEY=

# ── React ───────────────────────────────────────────────────
REACT_APP_API_BASE_URL=
```

**`GEMINI_API_KEY` is currently unset** (placeholder value in the working `.env`) — the backend detects this at startup and disables real Gemini calls, returning a fixed `"AI insight unavailable."` string instead of crashing. See [AI Insights](#ai-insights-gemini) below for what this currently blocks.

---

## Default Login

> ### ⚠️ **LOCAL DEVELOPMENT ONLY — NEVER DEPLOY THESE**
>
> **The credentials below are hardcoded in `_seed_default_users()` and are published in this README, so they are public knowledge. They must never be used in, or left active on, any real or internet-reachable deployment.** They exist so a fresh clone is usable immediately.
>
> Before any real deployment: change every one of these passwords, or delete the accounts entirely and create real ones through User Management. Seeding only happens when the `users` table is empty, so an already-seeded database will keep these accounts until someone removes them — deploying is not enough to clear them.

Three demo accounts are seeded automatically on first backend startup if the `users` table is empty (`_seed_default_users()` in `main.py`):

| Email | Password | Role | Super-admin |
|-------|----------|------|--------------|
| `admin` | `Admin@2025!` | Head of Technology | Yes |
| `hos` | `HoS@2025!` | Head of School | No |
| `user` | `Lect@2025!` | Lecturer (assigned `ICT104`, `ICT201`, `ICT301`) | No |

Use **User Management** (`/users`, super-admin only) to create additional accounts.

---

## Loading Data

Two source files are loaded automatically into in-memory pandas DataFrames **at backend startup** — this is the primary path, not a manual step:

| File | Contents | Notes |
|---|---|---|
| `data/Capstone_data_20260729.csv` (~35MB) | Assessment marks, one row per assessment item | Earlier snapshots live in `data/archive/` |
| `data/masked_attendance.csv.gz` (~9MB) | Class-session attendance, one row per student per session (2.5M rows) | **Stored gzipped** — 119MB uncompressed |

**Why attendance is gzipped:** the raw file is 119MB, which exceeds GitHub's 100MB per-file hard limit and would make the repo unclonable without Git LFS. Gzip brings it to ~9MB (92% smaller) with no code cost — `pd.read_csv()` decompresses `.gz` transparently, so every consumer (`main.py` startup, `build_attendance_features.py`, `train_model.load_attendance_raw()`) just points at the `.gz` path. Verified identical: both files parse to the same 2,517,435 × 11 DataFrame (`.equals()` → `True`), with no meaningful read-time difference (0.9s vs 0.8s).

To get a plain CSV back for inspection: `gunzip -c data/masked_attendance.csv.gz > /tmp/attendance.csv`.

`POST /api/ingest` also still exists as a runtime override (upload a different CSV/XLSX without restarting the container), matching the original **Data Ingestion** page's behavior, but it's a secondary path now, not the only way data gets in. Uploads are plain CSVs — the gzip storage applies only to the checked-in copy.

### Data Handling — what this system processes, and what is *not* guaranteed

**This system processes real student records, not synthetic data.** 7,926 distinct students, 327,501 assessment rows, and 2,517,435 attendance sessions, covering real assessment marks, real pass/fail outcomes, real class attendance, and demographic attributes (`AGEGROUP`, `GENDERCODE`, `COUNTRY_MASKED`).

**Masking is applied upstream, before the data reaches this project.** Direct identifiers arrive already replaced with sequential pseudonyms — `Student0`, `Student1`, … and `Country0`, `Country1`, …. No name, email, student number, or date of birth is present in either source file. Nothing in this repository performs the masking; this project is a consumer of already-masked extracts.

**Stated plainly, because it would be easy to overclaim here:**

- **The robustness of that masking has not been verified by this project, and could not be** — verifying it would require the unmasked source and the mapping, neither of which this project has ever had.
- **"Masked" is pseudonymisation, not anonymisation.** Whoever holds the upstream mapping can re-identify any row. The pseudonyms are stable and sequential across both files, which is what makes the student↔attendance join work at all — the same property that makes them a consistent key for anyone with the mapping.
- **Re-identification risk from quasi-identifiers has not been assessed.** Age group + gender + country + subject + study period + building, in combination, may well be unique for some students in a 7,926-student cohort. No k-anonymity or similar analysis has been run. This is a real, unmeasured risk, not a theoretical one.
No privacy guarantee beyond "direct identifiers were removed upstream" should be inferred from anything in this project.

#### DECISION (2026-08-13): this data is NOT acceptable in a public repository

Recorded as an explicit decision by the project owner, not left as a passive disclosure, because it had been flagged twice without being resolved.

**The situation as found.** On 2026-08-13 the GitHub API reported `"visibility": "public"` for `KOI-Capstone-Project/EDAPTv2` (0 forks, 0 stars, 0 watchers at that time). Committed to that repository's history and reachable by anyone:

| Path | Contents |
|---|---|
| `data/Capstone_data_20260729.csv` | ~34MB — real assessment marks and outcomes, 7,926 students |
| `data/archive/Capstone_data_20260324.csv` | an earlier extract of the same population |
| `data/masked_attendance.csv.gz` | ~9MB gz — 2,517,435 real class-attendance sessions |
| `backend/app/ml/models/model_20260808_110630.pkl` | model trained on that data |
| `backend/app/ml/models_simulated/model_20260808_113534.pkl` | model trained on that data |

**The decision: this is not acceptable.** Pseudonymised student records must not sit in a public repository, and the re-identification risk from quasi-identifiers listed above has never been assessed. Publication was not a deliberate data-handling choice; it is the state the repository happens to be in.

**Required remediation, in order:**

1. **Set the repository to Private.** This is the only step that stops ongoing exposure, and it is the one to do first. Everything below is cleanup that can follow.
2. **Scrub the data files from git history** — not just delete them from the tip. `git rm` leaves every blob in history and reachable by SHA. Use [`git-filter-repo`](https://github.com/newren/git-filter-repo) (preferred) or BFG:
   ```bash
   git filter-repo --path data/ --path-glob 'backend/app/ml/models*/*.pkl' --invert-paths
   ```
   This rewrites every commit, so it must be coordinated with anyone holding a clone, and the remote needs a force push afterwards.
3. **Re-supply the data outside git** — a private bucket, an institutional share, or a local-only path — and reduce `data/` in the repo to a schema description plus a small synthetic fixture. Note the real consequence: **CI's backend-tests job depends on the committed data and models**, so this step requires deciding how CI gets a dataset (synthetic fixture, or a secret-authenticated download), not just removing files.
4. **Assume the extract has been disclosed** for as long as steps 1 and 2 are outstanding, and tell whoever owns this data at KOI. "0 forks, 0 stars" is weak evidence of no access — it is not an access log.

**Not done automatically, deliberately.** Changing repository visibility and rewriting published history are both destructive and outward-facing, and neither is reversible by the person running them. They are the owner's to execute.

**No secrets were exposed.** Checked separately and independently of this: `.env` is gitignored, has never appeared in any commit tree in any revision, and a scan of all history for API-key, private-key and token patterns found no matches. The exposure here is student data, not credentials.

### Expected Columns — capstone marks

| Column | Description |
|--------|-------------|
| `STUDENTID_MASKED` | Anonymised student identifier |
| `SUBJECTCODE` | Subject code (e.g. `ICT205`) |
| `ASSESSMENTTYPECODE` | Assessment type code |
| `MARKPERCENT` | Mark as a percentage (0–100) |
| `WEIGHTING` | Assessment item's weight toward the final grade |
| `ATTEMPTNUMBER` | Attempt number for that assessment |
| `STUDYPERIOD` | Study period code (e.g. `25.3`) |
| `COUNTRY_MASKED` | Student's origin country (masked) |
| `GENDERCODE` | Gender code |
| `AGEGROUP` | Age group bracket |

### Expected Columns — attendance

| Column | Description |
|--------|-------------|
| `STUDENTID_MASKED` | Anonymised student identifier (joins to the capstone file) |
| `course` | Subject code — renamed to `SUBJECTCODE` on load |
| `year` + `study_period_code` | Combined into `STUDYPERIOD` on load (e.g. `2025` + `T3` → `25.3`) |
| `attendance_code` | `H` = present, `N` = absent unexplained, `A` = absent authorised |
| `class_no`, `actv_no`, `cls_session_no` | Class/activity/session identifiers — the only session-ordering signal available (there is no date field) |
| `location_code`, `building`, `room` | Campus, building and room — used for the building/pass-rate analysis in Known Open Items |

Only `ATTENDANCE_RATE` (share of `H`) is used as a model feature — see [Attendance as a model feature](#attendance-as-a-model-feature).

---

## Database

The `predictions`, `users`, and `audit_logs` tables are real and actively used. The remaining relational tables (`students`, `programs`, `trimesters`, `subjects`, `class_groups`, `lecturers`, `enrollments`, `assessments`) exist in `backend/app/db/models.py` but are **permanently empty** — nothing in the app writes to them, since real assessment data is served from the in-memory CSV dataframe, keyed by string identifiers (`"Student3340"`, `"ICT205"`, `"25.2"`), not by integer IDs into these tables. Building and maintaining a full CSV-to-SQL ETL into that unrelated schema would be a large, separate undertaking nothing in this codebase currently does.

### `predictions` — confirmed current structure (post-fix)

The table's original design FK'd `student_id`/`trimester_id` into the empty `students`/`trimesters` tables and had no subject column at all. It was rewritten to match how the rest of the app actually identifies things:

| Column | Type | Notes |
|--------|------|-------|
| `id` | BigInteger, PK | |
| `student_id_masked` | String(50) | Raw CSV identifier, e.g. `"Student3340"` |
| `subject_code` | String(20) | e.g. `"ICT205"` |
| `study_period` | String(10) | e.g. `"25.3"` |
| `model_version` | String(80) | Registry version id, or a simulated-progress model identifier |
| `predicted_pass` | Boolean | |
| `pass_probability` | Float, nullable | 0.0–1.0, from `predict_proba` |
| `risk_band` | String(20), nullable | Safe / At Risk / High Risk |
| `estimate_type` | String(30), nullable | `"mid-term estimate"` for simulated-progress predictions, `NULL` for complete-record |
| `actual_pass` | Boolean, nullable | Backfilled by `reconcile_predictions.py`; `NULL` until then |
| `reconciled_at` | DateTime, nullable | |
| `reconciled_via_resit` | Boolean, default `false` | `true` if `actual_pass` came from the resit-fallback reconciliation path rather than the standard attempt-1 check |
| `gemini_insight` | Text, nullable | |
| `predicted_at` | DateTime | |

Unique constraint on `(student_id_masked, subject_code, study_period, model_version)` — one row per student/subject/period/model-version combination, upserted on repeat predictions.

No migration framework (Alembic is a dependency but unused) — schema changes are applied via `Base.metadata.create_all()` on an empty table, or direct `ALTER TABLE` for tables with real data.

---

## ML Pipeline

### Model type and current live model

Two separate model families, both a soft-voting ensemble of **XGBoost + Random Forest**, trained via `train_model.py`'s Step 4:

Confirmed directly from `backend/app/ml/models/registry.json` (`live_version: 20260808_110630`):

| | Value |
|---|---|
| Subjects trained on | 124 (`fully_clean` + `mostly_clean` per `data/subject_reliability.json`, `TSL713` excluded) |
| Feature set | 11 features, including `ATTENDANCE_RATE` |
| Training row count | 65,903 (corrected labels) |
| Trained on | All periods before 25.3, excluding the 23.1 pilot period |
| Validated on | 25.3 |
| Accuracy | 0.9540 |
| Fail-class precision / recall / F1 | 0.7931 / 0.7809 / 0.7869 |
| PR-AUC (fail class) | 0.8808 |
| Decision threshold | 0.50 — an honest validation sweep put the value at 0.475, inside this project's own 0.03 noise band, so the deployed 0.50 was left unchanged (see `model_card.md` Round 10) |

**This model was promoted in Round 10, replacing `20260715_132655`.** Its recall (0.7809) is *lower* than the old model's headline 0.8374 — that is expected and correct, not a regression: Rounds 6/9 proved the old figure was inflated by one-directional label noise the old model had been trained on. On the same corrected test set the new model wins precision by **+6.05pp**, F1, and PR-AUC, and at matched recall it strictly dominates (R=0.8241/P=0.7362 vs R=0.8230/P=0.7326). Promotion required an explicit `--force` because the gate compares metrics measured on *different* test sets (953 vs 972 fails) — the full justification is recorded in the registry's `promotion_history`.

*(The previous live model's `0.8374` recall and the label-correction story behind it are documented in `model_card.md` Rounds 6, 9 and 10.)*

### Attendance as a model feature

`ATTENDANCE_RATE` was added to both models' feature sets — see `model_card.md`'s Round 7 for the full writeup, including the correlation check that ruled out also including `UNEXPLAINED_ABSENCE_RATE`/`ABSENCE_RATE` (the three sum to exactly 1.0 by construction, so including more than one is pure redundancy). Real findings:

- **100% match rate** for the complete-record model (74,831/74,831 enrolments) — no imputation was needed there.
- **Leakage-safe for the mid-term model, checked directly**: attendance is truncated to the same achieved-coverage fraction as that synthetic snapshot's marks (sorted by `class_no, actv_no, cls_session_no` — the only session-ordering field available; no real date exists in this dataset). A student's full/final attendance rate is never used to train the mid-term model — the same leakage class as the earlier 100%-accuracy mid-term incident this project already caught once.
- **SHAP-confirmed as a real, mid-tier factor** — ranked 6th of 11 features by mean |SHAP value|, not buried at negligible importance. Reconstruction check still holds (max deviation 6.01e-08).
- **Does not recover the Round 6 recall regression.** Adding attendance (plus the already-corrected labels, imbalance handling left untouched per a checked, not assumed, decision — see below) scores 0.7809 fail-class recall, marginally *below* the no-attendance corrected candidate's 0.7860, and still 4.21pp below the frozen live model's own new-data recall (0.8230). The one real positive is a small PR-AUC gain (0.8790 → 0.8808) — attendance carries real but weak signal that doesn't translate into better classification at the current threshold. **The Round 6 recall regression remains unexplained-by-a-fix and open.**
- **Class-imbalance handling was checked, not blindly re-tuned**: training-set fail-class proportion barely moved (12.42% → 12.24%, −0.18pp — far smaller than the 2.35pp shift found in the test period specifically), and the current SMOTE/RandomForest configuration already self-adjusts to whatever data it's given (no hardcoded ratio exists to "update"). No change was made, and this was a deliberate, evidence-based decision, not an oversight.
- **The mid-term/simulated-progress model is now live with this feature.** **Fixed since: this model family now has a real promotion gate (`sim_model_registry.py` / `compare_and_promote_simulated.py`) — see [Mid-semester prediction](#mid-semester-partial-progress-prediction) below for the full story; it did not have one when this attendance retrain first went live.** Real mid-term predictions now require and use attendance data.
- **A real bug was caught and fixed as a direct consequence**: retraining the mid-term model to 11 features broke `test_predict_shap_explanation_matches_live_model` (the cached `shap_background_simulated.pkl` still had 10 columns). Diagnosed and fixed by regenerating that one background file — `shap_background_main.pkl` (shared with the still-live, still-10-feature complete-record model) was deliberately left untouched throughout, to avoid breaking real, live explanations with a shape mismatch.

### Model card, ablation study, and a real calibration finding

Full detail in [`model_card.md`](model_card.md) — three rounds of real, evidence-based validation, including two places where an earlier round's own conclusion was corrected after a fairer test rather than left standing. Headlines:

- **Ensemble vs. single XGBoost**: an apples-to-apples comparison (both WITH SMOTE, isolating architecture as the only variable) found the ensemble's ranking-quality edge is not a real, repeatable gain (~0.2pp PR-AUC — smaller than this project's own established noise threshold). What *is* real: at the shared 0.50 threshold, the ensemble trades ~5 points of fail-class precision for a **+3.53 percentage-point fail-class recall gain** over a single XGBoost — confirmed to replicate almost exactly (+3.53pp vs. +3.53pp) on a second, independently-built validation period. The ensemble is kept for that recall advantage specifically — an explicit, quantified, non-performance-purity reason, not an assumed one.
- **SMOTE vs. class-weighting — a Round 1 finding that didn't hold up and was corrected, not left standing.** Round 1 claimed removing SMOTE collapses fail-class precision from 0.72 to 0.48; Round 2 found that comparison judged the no-SMOTE model at a threshold tuned for a *different* model's probability distribution. Given its own honestly re-validated threshold, the no-SMOTE model reaches precision 0.686 / recall 0.819 — close to the SMOTE model's 0.724 / 0.799, with marginally *higher* raw ranking metrics. Current position: neither SMOTE nor the ensemble has a demonstrated fair performance advantage — both are kept as reasonable working defaults, not as provably-best choices.
- **Dumb baseline check**: a trivial "flag if average score to date < 50%" rule with zero ML gets within ~1 percentage point of the full model's PR-AUC. The model's real value is a smooth, well-positioned probability and a usable precision/recall tradeoff — not a large raw ranking-quality gain over the obvious signal.
- **A real calibration problem in the complete-record model, and a real bug it helped surface**: the model ranks students correctly (ROC-AUC 0.974) but its raw predicted probabilities understate true pass likelihood by roughly 15–30 percentage points across the entire 10–90% predicted range — only the two extreme bands (~78% of students) are well-calibrated. **Correction**: this finding is about the **complete-record model** (`predict()`); it was previously cross-referenced elsewhere as being about the mid-term model, which was never actually checked at the time — see the mid-term-specific calibration check, now done, below. This calibration gap turned out to be the root cause of a real, reported production bug — see [Mid-semester (partial-progress) prediction](#mid-semester-partial-progress-prediction) below — fixed at the display level there, not at the root (a Platt/isotonic correction for the complete-record model itself remains open, tracked as a follow-up).
- **The mid-term model's own calibration was checked directly and corrected.** Raw predictions understate true pass likelihood even more than the complete-record model — mean absolute calibration error 13.33 percentage points across the 0–90% range, ROC-AUC 0.893 (a genuinely different, less-confident model, consistent with predicting off partial records). A Platt-scaling calibrator, fit on out-of-sample validation predictions, drops that error to 2.23pp with no change to ranking (ROC-AUC unchanged) or to which students get flagged Fail (the decision boundary is mathematically preserved by the monotonic transform). Implemented as a new **`probability_calibrated`** field on mid-term predictions, additive to the existing `probability` — not swapped in as the default, because doing so consistently would move the mid-term Safe floor from 70% to 95% (see next bullet), a real product-behavior change, not a small tweak. Full detail and the reliability tables in [`model_card.md`, Round 5](model_card.md).
- **A real, currently-harmless latent bug found in `build_target()`**: it sums every row for a student-subject-period with no `ATTEMPTNUMBER` filtering — if a student had both an original attempt and a resit for the *same* assessment type within an otherwise-"clean" (attempt-1-summing-to-~100%) enrolment, both attempts would be summed, inflating `FULL_WEIGHTED_FINAL` past 100% of the subject's weighting and potentially flipping the pass/fail label. Verified against the real, current dataset: this affects **0 of the 271,981 rows** that survive the existing SAFE_SUBJECTS + enrolment-cleanliness filter today — every real case where it could happen is already excluded by that filter for an unrelated reason. Not fixed as part of this pass (training-target logic change needs a deliberate decision); tracked in `model_card.md`'s Known Limitations.
- **The weighting-anomaly detection logic was tested against a genuine anomaly, independent of any override, and passed.** A synthetic subject with no manual-override involvement and a ~50%-incomplete enrolment was correctly flagged both at the enrolment level and the subject level — the mechanism that originally caught nothing for TSL713 (its issue needed a manual override; sum-based checks structurally can't see a same-total swap) does correctly catch genuine incompleteness.
- **The fairness-audit population-mismatch concern didn't hold up either, on inspection.** The underlying mechanism (nulls silently dropped from per-group breakdowns) is real in the code, but the real current test population has **zero null demographic values** in any of the three audited dimensions — so overall accuracy and every fairness breakdown are, today, computed on the identical population. Fixed anyway as a forward-looking robustness improvement (explicit `"Unknown"` category instead of a silent drop), verified via a real retrain to have zero effect on current numbers.

### Versioned model registry

`train_model.py` never overwrites a single model file. Every run saves to `models/model_<timestamp>.pkl` via `model_registry.register_version()` and is **never** made live automatically — `registry.json` currently tracks 8 versions. Registration and promotion are protected by an exclusive lock file (`.registry.lock`, atomic `O_CREAT|O_EXCL`) against concurrent-write races, with a 30-minute stale-lock auto-recovery and a 5-minute wait-then-fail-cleanly timeout for a live contender.

```bash
docker exec edaptv2_backend python3 -m app.ml.train_model               # train + register a new version
docker exec edaptv2_backend python3 -m app.ml.compare_and_promote --list             # list registered versions
docker exec edaptv2_backend python3 -m app.ml.compare_and_promote <version>           # report-only comparison against live
docker exec edaptv2_backend python3 -m app.ml.compare_and_promote <version> --promote # promote (refuses if fail precision/recall drops >3pp)
docker exec edaptv2_backend python3 -m app.ml.compare_and_promote <version> --promote --force  # promote anyway
docker exec edaptv2_backend python3 -m app.ml.compare_and_promote --rollback <version> # roll back to an earlier version
```

### Mid-semester (partial-progress) prediction

A **separate** model family, trained on synthetic partial-progress snapshots constructed from real, fully-graded enrolments (`train_simulated_progress.py` / `build_simulated_progress_features()`) — necessary because the real dataset is a closed, historical snapshot with no genuine partial records; an earlier attempt to reuse the complete-record model's feature definition on partial data produced 1.0000 accuracy, which was correctly diagnosed as target leakage rather than reported as a result.

**Fixed: this model family now has a real promotion gate, the same pattern as the complete-record model.** Until this session's attendance-feature retrain, `train_simulated_progress.py` wrote directly to `best_model_simulated_progress.pkl` — live immediately, no versioning, no comparison, no human review. That retrain went live ungated, and the gap was only caught afterward. **Real, urgent consequence found while investigating**: no backup of the pre-attendance version existed anywhere (it had never been git-tracked — `*.pkl` is gitignored — and the direct-overwrite pattern left no on-disk history). It was recovered only by chance, from inside a `edaptv2-prod-backend` Docker image built earlier the same session for unrelated testing (Item 8), which happened to `COPY` the file in before it was overwritten and had no `.dockerignore` excluding it. Had that image not existed, the pre-attendance version would have been unrecoverable.

Fixed properly, not just patched around that one incident:
- **`sim_model_registry.py`** — a sibling to `model_registry.py`, same pattern (versioned `models_simulated/model_<timestamp>.pkl` files, `registry.json`, an exclusive lock, explicit promotion only), pointed at its own directory rather than modifying the already-correct, already-in-production complete-record registry.
- **`train_simulated_progress.py`** now calls `register_version()` instead of overwriting the live file directly — every run is a new, timestamped, non-destructive version.
- **`compare_and_promote_simulated.py`** — the same refuse-if-fail-precision/recall-drops->3pp gate as `compare_and_promote.py`, reusing the identical threshold rather than re-deriving one.
- **`predictor.py`** now loads `_SIM_PACKAGE` from `sim_model_registry.load_live_model()`, not a hardcoded file path.
- **Real evidence the fix works**: the pre-attendance version (recovered from the Docker image) and the attendance version were registered with their real, honest history — the pre-attendance one first (backfilled as what was actually live before), then the attendance one compared against it on the identical test set. Real numbers: precision +0.25pp, recall **+0.67pp**, F1 +0.37pp, PR-AUC +0.33pp — the attendance version is not worse, it's marginally better on every metric, so it was promoted through the real gate (`compare_and_promote_simulated.py 20260808_113534 --promote`), not left live by default. Verified via the real CLI gate reporting "not meaningfully worse" before promotion, and the full backend test suite (21/21) passing after the switch, with the live model version and predictions unchanged from before the fix (same model, now properly versioned and gated instead of a raw file).

```bash
docker exec edaptv2_backend python3 -m app.ml.train_simulated_progress                                     # train + register a new version
docker exec edaptv2_backend python3 -m app.ml.compare_and_promote_simulated --list                          # list registered versions
docker exec edaptv2_backend python3 -m app.ml.compare_and_promote_simulated <version>                       # report-only comparison against live
docker exec edaptv2_backend python3 -m app.ml.compare_and_promote_simulated <version> --promote              # promote (refuses if fail precision/recall drops >3pp)
docker exec edaptv2_backend python3 -m app.ml.compare_and_promote_simulated <version> --promote --force       # promote anyway
docker exec edaptv2_backend python3 -m app.ml.compare_and_promote_simulated --rollback <version>              # roll back to an earlier version
```

Serving routes on coverage, computed server-side and never trusted from the client:

| Coverage | Tier | Model | API response |
|---|---|---|---|
| ≥ 99.5% | complete | `predict()`, live registry model | `estimate_type: null` |
| 50–99.5% | partial | `predict_partial()`, simulated-progress model, threshold re-selected per retrain (currently 0.30, historically 0.25) | `estimate_type: "mid-term estimate"` |
| < 50% | insufficient | none called | `coverage_status: "insufficient_data"`, prediction fields `null` |

**A real, reported production bug was found and fixed here**: a screenshot showed a mid-term prediction displaying 73.1% (green "Safe" badge) directly above the plain-text label "Fail" for the same prediction. Root cause: `predict()` and `predict_partial()` use different, independently and honestly validated decision thresholds (0.50 vs. 0.25 respectively), but the risk band (Safe / At Risk / High Risk) used to be one hardcoded 65%/40% split shared by both — since the mid-term threshold implies a Pass/Fail boundary at 75% (`100 × (1 − 0.25)`), which sits *above* the shared 65% Safe floor, any probability in 65–75% could be "Fail" by the label and "Safe" by the band simultaneously. Reproduced the exact reported case live, then fixed it at the shared source (`predictor.py`'s `_compute_risk_band()`, used by both prediction functions) rather than patching the frontend — the Safe floor is now derived from whichever threshold actually produced the label (`max(65, 100 × (1 − threshold))`), making the contradiction structurally impossible rather than just less likely. The mid-term model's honestly-validated 0.25 threshold was deliberately **not** changed to 0.50 to fix this — that would have silently discarded real validation work and reduced mid-term fail-detection recall. Two regression tests cover this (an HTTP-level reproduction and a pure unit-level sweep across five threshold values).

One direct, visible consequence: **mid-term predictions now show a different risk-scale legend than complete-record predictions** — the Safe floor is derived from each model's own threshold, currently 70% for mid-term vs. 65% for complete records (was 75% when the threshold was 0.25; it moves whenever either model is retrained). This is surfaced to the user, not just documented: the Predictor page shows a plain-language caption above the risk scale whenever a mid-term estimate is displayed, and — since a previous version hardcoded "75%" in that caption and went stale the moment this session's retrain moved the real threshold — the legend now reads the actual current value from the API (`predictor.py`'s `safe_floor_percent` field) rather than a hardcoded number, so it can't silently drift out of sync again. This banding fix is a **display-level fix for a deeper root cause** — the mid-term model's calibration gap, now measured and corrected as an additive `probability_calibrated` field (see the calibration finding above and `model_card.md`'s Round 5) — but re-testing showed unifying the two scales is *not* a natural consequence of that fix; if anything the floors diverge further once calibration is accounted for. `model_card.md`'s Round 5 has the full writeup.

### Explainability (SHAP)

Confirmed present and wired into serving: `backend/app/ml/explain.py` computes real per-feature SHAP attributions for every prediction, using `shap.TreeExplainer` on each of the ensemble's two sub-models separately (XGBoost + Random Forest), averaged — exact, not approximate, since soft voting with no explicit weights is itself an equal-weight average and SHAP values are linear in the value function being explained. Verified: reconstructing `base_value + sum(shap_values)` matches the ensemble's actual output to ~1e-8. Both `predict()` and `predict_partial()` responses include a `shap_explanation` field; a dedicated test (`test_predict_shap_explanation_matches_live_model`) checks this against a live server response for both models. The frontend shows the top 3 real factors as directional bars, and feeds those same real numbers (not a free-form prompt) into the Gemini "AI Assisted Insight" text.

Background data for SHAP's interventional mode is cached to disk (computing it live costs ~55s for the simulated-progress model — too slow for every backend startup):

```bash
docker exec edaptv2_backend python3 -m app.ml.build_shap_background
```

**Known open item**: whether Gemini's generated sentence stays grounded in the real SHAP numbers it's fed, or drifts into inventing plausible-sounding reasons, has not been verified — `GEMINI_API_KEY` is currently a placeholder in `.env`, so every Gemini call returns a fixed unavailable message rather than real generated text. The prompt-construction side is verified correct; the model-behavior side isn't testable in this environment yet.

### Automated retraining infrastructure

- **Dynamic period resolution** (`resolve_periods()` in `train_model.py`) — test period is always the latest `STUDYPERIOD` present in the raw data, validation the second-latest, train everything before. No hardcoded period constants.
- **New-period detection**: `check_new_period.py` compares the latest period in the raw data against the live model's `validated_on`.
- **Scheduler**: `scheduled_retrain.py` checks for a new period and, if found, retrains and registers a candidate (never promotes). Also re-runs an honest threshold validation sweep on every retrain and reports (does not auto-apply) whether the optimal decision threshold has drifted from 0.50 by more than 3 percentage points. Wired into a Docker Compose sidecar (`backend/scripts/retrain_loop.sh`: run once, sleep 24h, repeat) — opt-in in dev via `--profile scheduler`, always-on in prod.

```bash
docker exec edaptv2_backend python3 -m app.ml.check_new_period
docker exec edaptv2_backend python3 -m app.ml.scheduled_retrain           # only retrains if a new period is detected
docker exec edaptv2_backend python3 -m app.ml.scheduled_retrain --force   # retrain regardless
```

### Outcome tracking and reconciliation

Every real prediction (one with a known `student_id`) is logged to the `predictions` table. `reconcile_predictions.py` backfills `actual_pass` once a student-subject-period enrolment is fully graded, using the same clean-enrolment logic training uses, plus a resit-fallback pass (a student's latest attempt, when no attempt-1 record exists) tagged separately via `reconciled_via_resit` rather than silently merged.

```bash
docker exec edaptv2_backend python3 -m app.ml.reconcile_predictions
docker exec edaptv2_backend python3 -m app.ml.prediction_accuracy_report   # predicted-vs-actual accuracy, by model version / estimate type / reconciliation method
```

### Fairness / bias auditing

`train_model.py`'s Step 6 persists a `bias_audit` dict (in both the model `.pkl` and `registry.json`) breaking out fail-class precision/recall/F1 by country, gender, and age group, flagging any group more than 10 percentage points off the overall rate. `check_bias_persistence.py` tracks whether a flagged group recurs across independent retrains (deduplicated by training period, since a re-run on identical data isn't a second data point) versus appearing once:

```bash
docker exec edaptv2_backend python3 -m app.ml.check_bias_persistence
```

**Current finding, stated at its real confidence level**: age group 0–20 (n=139) is flagged (fail-class recall −10.2pp vs. overall) — but only **one** independent, distinct-period audit has been persisted so far, so this is a single observation, not yet a confirmed trend.

---

## Running Tests

```bash
docker exec edaptv2_backend pytest tests/ -v
```

**24 tests, all passing** as of this README (regenerated via `pytest --collect-only`, not hand-typed — `test_smoke.py`'s 16 plus `test_ingestion_e2e.py`'s 8, on a container built `--no-cache` from `requirements.txt`) — covering health/auth, the three coverage-tier prediction paths, server-side recomputation of partial scores (regression test for the train/serve consistency bug), SHAP explanation consistency for both models, the Fail/Safe risk-band contradiction fix (both an HTTP-level reproduction of the reported bug and a pure unit-level invariant sweep across five threshold values), the roster's server-side feature-assembly path for both coverage tiers, cross-endpoint agreement on a real student's attendance rate, the two-phase ingestion flow's Postgres-backed pending-row handoff (including a real cross-process lock-contention test and a TTL-expiry test against a genuinely backdated row), and column classification.

---

## AI Insights (Gemini)

| Tier | Endpoint | Trigger | Scope |
|------|----------|---------|-------|
| 1 — Auto Alert | `POST /api/gemini/alert` | On page load | Subject + trimester |
| 2 — Deep Analysis | `POST /api/gemini/analyse` | Click button | Subject + trimester |
| 3 — Free Q&A | `POST /api/gemini/ask` | User question, or auto-generated per-prediction question fed real SHAP factors | Subject + trimester |

Admin-level equivalents (`/api/gemini/institution-*`) serve the Admin Dashboard with institution-wide context.

Set `GEMINI_API_KEY` before starting the backend. Without a real key, every call returns a fixed `"AI insight unavailable."` string rather than crashing — confirmed this is the current live state of this deployment.

---

## Authentication

- JWT tokens stored in `localStorage` as `edapt_token`
- User profile stored as `edapt_user` (JSON)
- Tokens expire after 8 hours
- Role checking happens on both the frontend (route guards in `App.js`) and the backend (`require_admin` / `require_super_admin` FastAPI dependencies in `main.py`)

---

## API Overview

| Group | Key Endpoints |
|-------|----------------|
| Auth | `POST /api/auth/login` · `logout` · `change-password` |
| Dashboard | `GET /api/dashboard/summary` · `grade-distribution` · `performance-trend` · `assessment-comparison` · `pass-fail` · `international` · `difficulty-index` |
| Explorer | `GET /api/explorer/records` · `filters` · `student/{id}` · `export` |
| Subjects | `GET /api/subjects/list` · `analytics` · `{subject}/roster` · `{subject}/assessments` |
| Ingest | `POST /api/ingest` · `GET /api/ingest/preview` |
| ML | `POST /api/predict` (routes to complete-record, mid-term-estimate, or insufficient-data based on server-computed coverage; includes `shap_explanation`) |
| Gemini | `POST /api/gemini/alert` · `analyse` · `ask` · `institution-alert` · `institution-analyse` · `institution-ask` · `GET /api/gemini/token-log` |
| Users | `GET /api/users` · `POST /api/users` · `PUT /api/users/{email}` · `DELETE /api/users/{email}` |
| Audit | `GET /api/audit-logs` |

Full interactive docs: `http://localhost:8000/docs`

---

## Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Stable, reviewed code — `origin/main` is currently **10 commits behind** `ml_model` |
| `ml_model` | Active development — **currently ahead of `main` by all of the work described in this README**, committed and pushed to `origin/ml_model` |
| `sangam_dev` | Earlier development branch, superseded — 9 commits behind `ml_model` and 0 ahead (fully contained, not divergent). Not where current work lives |

PRs are opened from `ml_model` → `main`.

---

## Known Open Items

Stated plainly rather than rounded up or omitted:

- **Gemini drift verification is blocked**, not resolved — whether Gemini's generated text stays grounded in the real SHAP numbers it's fed has never been tested against a live model, since no real `GEMINI_API_KEY` exists in this environment.
- **The age 0–20 fairness finding is still a single observation**, not a confirmed trend (see [Fairness / bias auditing](#fairness--bias-auditing)) — re-checked directly via `check_bias_persistence.py` after this session's data refresh: still only 1 distinct (trained_on, validated_on) period pair (`25.3`) in the registry, because the refreshed capstone file corrected existing rows within the same period range rather than introducing a genuinely new study period. Not enough independent retrains yet to call this a trend either way.
- **The complete-record model's predicted probabilities are meaningfully miscalibrated in the 10–90% range** (see [model card](model_card.md)) — ranking is correct, the displayed percentage isn't literally trustworthy outside the two extreme bands. No calibration correction has been applied to this model yet (the mid-term model's was — see below). This is also the confirmed root cause of the Fail/Safe UI bug (fixed at the display level — see [Mid-semester prediction](#mid-semester-partial-progress-prediction) — but not at the root).
- **Checked, not assumed: calibrating the mid-term model does NOT let the two risk-band scales unify — it makes them diverge further.** The mid-term model's calibration was fixed (Platt scaling, MACE 13.33pp → 2.23pp — see `model_card.md`'s Round 5). Re-tested directly whether this lets the dual-scale UI workaround collapse back into one: it doesn't. The mid-term model's honestly-validated decision threshold (currently 0.30, re-selected on this session's refreshed data) corresponds to a *calibrated* fail-probability of only 0.054 — plugging that into the existing Safe-floor formula would push the mid-term floor from 70% to **95%**, not down toward the complete-record model's 65%. Real unification would need calibrating both models consistently and likely redesigning `_compute_risk_band`'s floor formula itself, not just fixing one model's calibration — a bigger, separately-scoped follow-up, not attempted here.
- **Checked, not assumed: the live ensemble's XGBoost hyperparameters are near-optimal.** A 36-point grid search (`max_depth ∈ {3,4,5,6}`, `learning_rate ∈ {0.01,0.05,0.1}`, `n_estimators ∈ {100,200,300}`) on the validation split found one candidate that looked like a free +1.13pp recall improvement, but registering it as a real candidate and re-checking with a same-data, same-split control (to separate the hyperparameter effect from this session's data refresh) showed the effect doesn't replicate — it's a wash (−0.5pp recall) once data and split are held constant. See [model card, Round 4](model_card.md) for the full isolation. Two experimental versions are registered but not live (`20260807_134847`, `20260807_135223`) — neither promoted, per the standing never-auto-promote rule.
- **The 5.13pp recall gap between the live model and a same-hyperparameter retrain on refreshed data has been fully investigated and its mechanism confirmed — not just flagged, not left as a correlation.** Full evidence and the quantified breakdown are in `model_card.md`'s Round 6. Short version: this session's data refresh corrected 205 real enrolments' PASS label from Fail to Pass (zero flips the other direction — confirmed one-directional, not noise) within period `25.3`, on an essentially identical roster (8,928 of 8,934 enrolments present in both old and new data — this is corrected labels, not new students from calendar time passing). **The mechanism is confirmed, not correlated: all 205 of the 205 flipped enrolments (100%) trace to the refreshed extract containing additional resit/attempt records these students didn't have in the old extract — `collapse_attempts_to_latest_per_type()` is confirmed correct on both inputs, it just had richer attempt history to work with in the new data.** Re-scoring the exact frozen live model against the corrected data alone drops recall to 0.8230 (a 1.9pp effect); retraining on the corrected data drops it further to 0.7860 (a further 3.7pp effect from the training data itself now reflecting corrected labels). **Stated plainly: `0.8374` should not be cited as the live model's current fail-class recall — it was partly earned against ground truth later shown wrong for 205 real students. `0.7860` is the more trustworthy figure as of 2026-08-08, even though it's numerically lower.** This is not period-to-period noise (a 100%-one-directional flip pattern isn't sampling variance) and not a new pipeline bug needing a fix (the resit-collapsing logic is confirmed correct on both the old and new data) — it means the live model needs re-validation against current data. **RESOLVED in Round 10**: the decision was made and executed — `20260808_110630` (corrected labels + attendance) was promoted and is now the live complete-record model, after an honest validation-derived threshold check and a full-metric comparison. See `model_card.md` Round 10 for the comparison table and the recorded `--force` justification.
- **Attendance was added as a real feature specifically to try to recover this recall gap — checked directly, it does not.** A candidate combining `ATTENDANCE_RATE` with the corrected labels (`20260808_110630`) scores 0.7809 fail-class recall — marginally *below* the no-attendance corrected candidate's 0.7860, not an improvement, and still 4.21pp below the frozen live model's own new-data recall (0.8230). See [Attendance as a model feature](#attendance-as-a-model-feature) above and `model_card.md`'s Round 7 for the full comparison table and the (checked, not blindly performed) decision not to re-tune class-imbalance handling. **Superseded by `model_card.md`'s Round 9 — there is no recall regression to fix.** A matched-control experiment, repeated across 25 independent random draws, showed the gap is not primarily caused by attendance, hyperparameters, or a shrinking fail class: flipping 223 *random* fails costs 0.70pp recall on average (std 0.44pp), while the 223 *real* corrections cost 2.98pp — 5.2 standard deviations out, below all 25 draws. So quantity contributes ~23% and the identity of the corrected rows ~77%. The corrected enrolments are systematically borderline passers, so the *old* labels contained one-directional noise that biased the old model toward predicting Fail — inflating its recall and depressing its precision. Every retrain beats the frozen model on F1 and PR-AUC, and at matched recall (threshold ≈0.405) the corrected-labels retrain equals or beats it on precision too. Attendance remains a real, SHAP-confirmed mid-tier feature; it simply was never the fix for a gap that turned out not to be a deficit. **Round 10 closed this out**: judged at an honest threshold on the full metric set, the corrected+attendance model has the best PR-AUC of all four candidates and was promoted to live.
- **Fixed, but with a real near-miss along the way: the mid-term model had no promotion gate, and the attendance retrain went live ungated.** Discovered urgently after the fact — see [Mid-semester prediction](#mid-semester-partial-progress-prediction) above for the full account. Worth stating plainly here: the pre-attendance model version had **no backup anywhere** (never git-tracked, direct-overwrite pattern) and was only recoverable by chance, from inside an unrelated Docker image built earlier the same session. Comparison (once recovered) showed the new version was not worse — precision +0.25pp, recall +0.67pp — so it was promoted through the newly-built gate rather than rolled back. The gate itself (`sim_model_registry.py`, `compare_and_promote_simulated.py`) is real and now in place, so this specific failure mode — an unvalidated model silently going live with no way back — cannot recur on the next retrain. **That comparison was afterwards re-checked for a confound and confirmed clean** (`model_card.md` Round 8): because the baseline was recovered from a Docker image rather than produced by a controlled experiment, it was not self-evident that it shared the attendance version's corrected-label training data — and the label correction alone is worth −3.7pp recall on the complete-record model, enough to swamp a +0.67pp signal. Verified two independent ways: both versions store `Fail support = 3,725`, which matches the post-correction split exactly (pre-correction data yields 34,028 rows / 4,516 fails), and each version's stored metrics reproduce to four decimals when re-scored on the current corrected test set. The two differ only by `ATTENDANCE_RATE` (10 features vs. 11), so the +0.67pp is a genuine isolated attendance effect.
- **`build_target()` has a real, currently-harmless latent bug**: no `ATTEMPTNUMBER` filtering, so a same-assessment-type resit within an already-"clean" enrolment would be double-counted. Verified this affects 0 real rows today (an unrelated existing filter happens to exclude every case where it could occur), but it's not a guaranteed protection for future data. Not fixed — needs a deliberate decision on training-target logic.
- **The prod scheduler sidecar was verified scoped** (image build, non-root permissions, error-resilience, and — this session — real cross-container file sharing with `backend_prod` via `docker compose -f docker-compose.prod.yml up db backend scheduler`), not against the full running prod stack (nginx/frontend-prod alongside it) — that fuller verification remains out of scope.
- **Fixed: the two-phase ingestion flow's pending-upload handoff is now Postgres-backed (`PendingIngest`, `app/db/models.py`), not an in-memory dict.** Prod confirmed to run 4 gunicorn workers (`docker-compose.prod.yml`, `--workers 4`) — separate OS processes that don't share Python state, so the old in-memory dict would have made `analyze`/`confirm` unusable whenever a non-sticky load balancer routed them to different workers. Proven with a real cross-process test (`test_confirm_works_from_a_pending_row_it_never_wrote_itself`): a pending row is written via a completely independent DB session, never through the `analyze` endpoint, and `confirm` still succeeds — real proof it depends only on the shared DB row, not any in-process object.
- **Fixed in both dev and prod: the scheduled retrain sidecar and ingestion-triggered retraining now agree on the current data file.** `train_model.DATA_PATH` resolves to `<INGESTED_DATA_DIR>/ingested_capstone.csv` (ingestion's writable copy) when present, falling back to the archived `data/Capstone_data_20260729.csv` otherwise — checked fresh at import time, so any independently-invoked process (a manual `check_new_period.py` run, or the scheduler's `python -m app.ml.scheduled_retrain`, a fresh process every 24h cycle) picks it up. Verified live in dev: ingested a small test file with a fake period (`99.2`), then ran `check_new_period.py` as a genuinely separate process — it reported `Latest period in raw data: 99.2`, not the archived file's `25.3`. **The prod gap is now fixed, not just documented**: `INGESTED_DATA_DIR` is a new env var (defaults to this file's own directory, preserving dev's existing bind-mount behavior unchanged) that `docker-compose.prod.yml` sets to `/shared_data` for both the `backend` and `scheduler` services, backed by a new named volume (`ingested_data_prod`) mounted into both — genuinely shared in prod now, not just baked-source-per-container. Verified against real prod images, not assumed: built `Dockerfile.prod`, brought up `db` + `backend` + `scheduler` from `docker-compose.prod.yml` (scoped — nginx/frontend-prod intentionally excluded, per this pass's own scope boundary), wrote a file from inside `backend_prod` into `/shared_data`, and read it back from inside `scheduler_prod` — succeeded, and `scheduler_prod`'s own `train_model.DATA_PATH` correctly resolved to the shared file once present. **A real permissions bug was caught and fixed in the process**: a fresh named volume is root-owned by default, which the non-root `edapt` user (`Dockerfile.prod`) couldn't write to — first attempt failed with `Permission denied`. Fixed by creating `/shared_data` with correct ownership in the image *before* `USER edapt` — Docker initializes a new named volume's ownership from whatever already exists at the mount path, so this makes it writable from first boot. Re-verified after the fix: write/read succeeded cleanly. A Postgres-backed version of this (storing the ingested CSV as a row instead of a shared-volume file, alongside `predictions`/`audit_logs`/`users`) was considered as the more architecturally consistent long-term option and is documented precisely enough to implement later without re-investigation in `train_model.py`'s `INGESTED_DATA_DIR` docstring — not done here since it touches every `DATA_PATH` consumer (`train_model.py`, `check_new_period.py`, `scheduled_retrain.py`) plus the ingest-confirm write path, a larger change than this pass's scope.
- **`location_code`, `building`, and `room` (from `masked_attendance.csv.gz`) show real variation in pass rate — partially, not fully, explained by which subjects are taught where.** The raw, unconditional `building` pass-rate spread is 9.7pp (78.2%–87.9%), but checked directly against the obvious confound: 128 of 129 subjects are taught in 2+ buildings, so a subject-adjusted comparison (each enrolment's PASS residual against its own subject's mean, averaged per building) is possible and was run. Result: the spread shrinks to 5.19pp (46% shrinkage) — subject explains roughly half the raw effect, but a real, subject-independent signal remains. That remainder is concentrated almost entirely in one building (`DARBY`, −4.58pp even after adjustment) — the other five buildings cluster within ~1.2pp of each other post-adjustment, so this isn't a smooth "building quality" gradient, it's specific to DARBY.

**DARBY was investigated directly — one candidate cause ruled out, one real-but-weak candidate found, one uncheckable, no full explanation found.** DARBY is 99.99% `location_code=NC` (essentially the sole in-person NC-campus building), so campus was the obvious next suspect — checked directly using `ONL`, the one building with a genuine NC/SC split: within `ONL` alone, NC vs SC residuals are virtually identical (−0.0078 vs −0.0075), and DARBY vs other NC-campus records (holding campus constant) still shows a real gap (−0.046 vs −0.010) — **campus is ruled out**, DARBY's effect isn't a campus effect wearing a building label. Class size was checked next: DARBY's average class size (13.6 students/session, the smallest of all 6 buildings) correlates with the subject-adjusted residual at r=0.11 across the whole dataset — real but weak (~1% of variance), directionally consistent with DARBY's gap but nowhere near sufficient to fully explain a −6.5pp session-group-level residual gap on its own. Time-of-day couldn't be checked at all — the data has no clock-time field, only `cls_session_no` (a within-activity sequence number, not a real time). **Honest conclusion: no full explanation found** — campus is ruled out, class size is a real partial contributor, and DARBY's remaining gap is unexplained by what's available in this dataset. A real, deliberate follow-up task if pursued further would need a data source this project doesn't have (actual class scheduling/time-of-day data), not a re-analysis of what's already here.
- **Deliberately left unverified: the other endpoints that assemble model features server-side.** Two real bugs this session lived in exactly that pattern — the roster returning `probability: null` for every student, and `/api/predict` disagreeing with the roster about the same student's attendance. Both were in code where *the server* builds the feature vector from stored data, rather than the client supplying it. **The same pattern is untested in `/api/subjects/{subject}/analytics`, the attendance analytics endpoints, and every dashboard endpoint beyond `/api/dashboard/summary`.** These are **not known to be broken** — no failure has been observed in any of them, and no claim is being made that one exists. They are named because they sit in the same blind spot that hid both confirmed bugs, which makes them the most likely place a similar issue would be found if one is there. **Checking them was a deliberate decision to stop, not an oversight** — the session's scope closed with the two known bugs fixed and the pattern documented, rather than expanding into an open-ended audit. Whoever picks this up next has a clear starting point: call each of those endpoints as a real client and assert on the values in the payload, not the status code. See [Testing Practices](#testing-practices--a-real-outage-the-suite-missed) for why HTTP 200 is not evidence here.
- **No GitHub-hosted CI run has been observed yet.** The pipeline in `.github/workflows/ci.yml` was proven locally with `act` and by running each job's exact commands, including a deliberate failure and recovery for every gate (see [CI and quality gates](#ci-and-quality-gates--automating-what-used-to-depend-on-remembering)). But no `gh` CLI or API token existed in the environment where it was written, so the first real run on GitHub's runners is still unverified. Two things could plausibly differ there: the `services:` Postgres wiring, and `--network host` reaching it. **Check the CI badge at the top of this file** — that, not this paragraph, is the current truth.
- **Type-checking is absent.** mypy was deliberately not added at close-out (rationale in the CI section). A real gap, named as one.
- **This feature set is committed and pushed on `ml_model`, but not merged to `main`** — `origin/main` is 10 commits behind. See the note at the top of this file.

---

## Testing Practices — a real outage the suite missed

A complete prediction outage ran undetected across several rounds of "21/21 passing, verified live" reporting. It is documented here rather than quietly fixed, because the cause was structural and the same shape of gap could hide other failures.

**What broke.** After an 11-feature (attendance-using) model went live, the roster endpoint was still calling the model without `attendance_rate`. `predict()` returns an error dict for a missing required feature, and the roster endpoint folds that into `probability: None` rather than raising — so every row came back `HTTP 200` with `probability: null`. The mid-term tier had been broken this way since its model was promoted; the complete-record tier broke when its model was promoted later. An unrelated promotion exposed it.

**Why 21 green tests missed it.** Every prediction test posted hand-built `assessments_used` to `/api/predict` — the path where *the client supplies every feature*. **No test touched `/api/subjects/{subject}/roster`**, the path where *the server assembles features* from stored data (`_DATA` marks + `_ATTENDANCE` lookups) before calling the model. The suite covered one half of the serving surface and reported it as coverage of the whole. Nothing asserted a probability was non-null, either — only status codes, routing and labels.

**Same-shape risks elsewhere** (server-assembles-features paths with no equivalent test): `/api/subjects/{subject}/analytics`, the attendance analytics endpoints, and the dashboard endpoints beyond `/api/dashboard/summary`. These are not known to be broken — they are named because they sit in the same blind spot.

**Fixed with a test proven to catch it.** `test_roster_complete_record_returns_real_predictions_not_nulls` and `test_roster_midterm_tier_returns_real_predictions_not_nulls` hit the real endpoint as a client would, for a subject/period discovered from live data, and assert every scorable row gets a real probability. Both were verified by deliberately re-introducing the bug: **both failed, then passed again once the wiring was restored** (and the restored file was confirmed byte-identical to the committed fix). A test that has never been seen to fail is not evidence.

**Going forward: any endpoint that assembles model features server-side needs a test that calls it as a real client and asserts on the prediction value, not just the status code.** HTTP 200 with a null payload is exactly what this suite was blind to.

**A second gap, found later in the same area: two endpoints can each be individually correct and still disagree with each other.** Once both roster tiers returned real predictions, `/api/predict` and the roster were *still* resolving attendance differently for the same real student — the roster used that student's own rate (`0.6923`), while `/api/predict` ignored `req.student_id` entirely and fell back to the subject average (`0.6220`). Same person, two numbers, depending which screen you opened; the same shape as the Fail/Safe risk-band contradiction. Every per-endpoint test passed throughout. Fixed at the shared source — both endpoints now resolve attendance through one function, `_resolve_attendance_rate()` — and covered by `test_predict_and_roster_agree_on_a_real_students_attendance`, which was proven by re-introducing the old behaviour (it failed, naming the exact student and both numbers, then passed once restored). **Where two endpoints answer the same question about the same entity, one of them agreeing with itself is not coverage — something has to assert they agree with each other.**

## Source-control note — a claimed fix that was never on disk

The roster wiring above was reported as written in an earlier round, then found missing. Investigated against real history rather than assumed:

`git log --all -- backend/app/main.py` shows the file in 3 commits this session. Searching each for the wiring: commit `0d0b3e5` and `addb00e` each contain exactly **two** `attendance_rate=` call-site arguments — both in `/api/predict` — and their roster branch calls the model with none. The distinctive roster comments appear in **no commit before `e80d357`** (the fix). **The wiring was therefore never committed, and never on disk at commit time — there was no revert.** An earlier note in this project speculated that an editor or workflow might be reverting `main.py`; that is ruled out and was wrong.

Checked for mechanisms that could discard uncommitted work: **no git hooks** (only `.sample` files), **no `git checkout`/`reset`/`clean`/`stash` in any repo script**, and the dev `Dockerfile` does not `COPY` app source over the `./backend:/app` bind mount. No mechanism found. The honest conclusion is that the edit was reported as applied but never persisted — a tooling/process failure on the authoring side, not a repository defect.

**Mitigation, since no environment cause exists to fix:** commit at the end of each unit of work rather than batching many rounds into one commit, and verify a claimed change is actually present (`grep` the file, or `git show <commit>:<path>`) before reporting it as done — the check that finally caught this.

## Container drift — the verification environment was not the project

Every test result reported across an entire session ran on a container that could not have been reproduced from this repository. This is recorded with the same prominence as the two incidents above because it is more serious than either: it undermines the *evidence* for the other fixes, not just one endpoint.

**What happened.** `shap` was hand-installed into a long-running dev container at some point and never existed in the image built from `requirements.txt`. The container kept running, so the package kept working, and the suite kept reporting green. A clean `git clone` + `docker compose up` would **not** have produced that environment.

**How it was found.** Not by a test — by an unrelated fix. Correcting the `SECRET_KEY` required `docker compose up -d --force-recreate backend`, because `docker restart` does not reload `.env`. The force-recreate destroyed the container and rebuilt it from the actual image, and the suite immediately dropped to **10 failed, 13 passed** — every failure a `ModuleNotFoundError: No module named 'shap'`. The hand-installed state had been the only thing holding it up.

**Real evidence.**

| Fact | Value |
|---|---|
| Commit that added `shap==0.52.0` to `requirements.txt` | `5fd48d8`, **2026-07-24** |
| `backend/requirements.txt` working-tree mtime | **2026-07-16** |
| Creation timestamp of the image actually in use | **2026-07-08T14:04:23Z** |
| `pip show shap` inside the recreated container | `Package(s) not found` |

The image predated the commit that introduced the pin by **16 days**. It was never capable of containing `shap`.

**The real implication, stated plainly.** Test results reported as passing in earlier rounds of that session were not necessarily reproducible from the actual repository contents. For an unknown portion of the session, the verification environment was not representative of the real project — so "the suite passes" was evidence about a hand-patched machine, not about this codebase. The subsequent clean-build run is the first result in that session that is known to describe the repository itself.

**Fix.** `docker compose build backend` resolved it with **no source changes** — the pin in `requirements.txt` was already correct. The defect was entirely in the environment having diverged from its own source of truth. After the rebuild: `pip show shap` → `0.52.0`, and the full suite passes.

**Going forward: periodically rebuild the dev image from `requirements.txt` (`docker compose build --no-cache backend`) rather than trusting a long-running container, and treat any `pip install` inside a running container as a change that must be written back to `requirements.txt` immediately.** A long-lived dev container silently accumulates unpinned state; the longer it runs, the less its green test suite means. Before reporting a result as verified, it is worth knowing whether the container it ran in could still be rebuilt from the repo.

## CI and quality gates — automating what used to depend on remembering

Every incident documented above was caught by a person deciding to check, not by tooling: the null-prediction outage, the fix that was never on disk, the hand-patched container. That is the actual gap this section closes. Each gate below was verified by making it fail on purpose first — the same standard this project already applies to code fixes.

### What runs, and when

| Gate | Where | Trigger |
|---|---|---|
| `ruff check` (backend lint) | `.github/workflows/ci.yml` → `backend-lint` | every push and PR |
| Fresh `--no-cache` image build | `backend-tests` | every push and PR |
| Image-vs-`requirements.txt` assertion | `backend-tests` | every push and PR |
| Full backend suite (24 tests) inside that image | `backend-tests` | every push and PR |
| `npm ci` + eslint + frontend tests | `frontend` | every push and PR |
| ruff, whitespace, YAML/JSON validity, large files, private keys, conflict markers | `.pre-commit-config.yaml` | every local commit |

### The build is deliberately uncached

`docker build --no-cache` is the point of the backend job, not an incidental flag. This project ran an entire session of green tests inside a long-lived container with `shap` hand-installed and absent from the image built from `requirements.txt` (see [Container drift](#container-drift--the-verification-environment-was-not-the-project)). Building fresh every run means CI can only pass against what `requirements.txt` actually specifies.

A second step asserts, for every pinned line in `requirements.txt`, that the package is installed in the built image at exactly that version. **`pip install --dry-run` was tried first for this and rejected: it exits 0 and merely prints "Would install X" when a package is absent, so it would have sailed straight through the shap incident.** The replacement uses `importlib.metadata` and exits non-zero.

### Proof each gate actually fails

Not "the config looks right" — each was made to fail on purpose:

- **Backend lint.** A file with an unused import and an undefined name was added and the job run locally with [`act`](https://nektosact.com): `❌ Failure - Main ruff check`, `Error: Job 'Backend lint (ruff)' failed`, citing `F401` and `F821`. Removed → job passes, `All checks passed!`.
- **Backend tests.** `shap==0.52.0` was deleted from `requirements.txt`, then the job's exact commands run: `docker build --no-cache` followed by pytest in the resulting image → **11 failed, 13 passed**, every failure a `ModuleNotFoundError: No module named 'shap'`. Restored → **24 passed**. This is the container-drift incident reproduced and then caught by the pipeline that now guards against it.
- **Requirements assertion.** Run against the correct image → passes. Run against the same image with `pip uninstall shap` → exits 1 with `shap: NOT INSTALLED (requirements.txt pins 0.52.0)`.
- **Frontend.** Whole job run under `act`: `npm ci`, lint, and 3 tests all green, `Job succeeded`.
- **Pre-commit.** A staged file with an unused import, an undefined name and trailing whitespace was committed: blocked, with `HEAD` verified unmoved and the file confirmed absent from every commit. Violations fixed → commit succeeded.

**Honest limitation on the CI proof.** There is no `gh` CLI or API token in the environment where this was set up, so no GitHub-hosted run could be observed. Everything above was proven with `act` running the real workflow file locally, plus direct execution of the job's exact commands. Two known differences: act's runner image lacks `node`, so the `actions/setup-python` post-step cleanup errors after the real steps pass ([nektos/act#107](https://github.com/nektos/act/issues/107)); and the backend-tests job was executed command-by-command against the local Postgres rather than through act's service containers. **The first GitHub-hosted run is therefore still unobserved — check the badge at the top of this file.**

### Linting decisions, and what was deliberately not done

Ruff was chosen over flake8: it covers flake8's rules plus import sorting and bugbear/comprehension sets in one pinned binary, so CI and pre-commit need one dependency rather than four.

Real numbers from the first run against this codebase, with what was done about each:

| Finding | Count | Action |
|---|---|---|
| `UP045` `Optional[X]` → `X \| None` | 114 | **Rule not enabled.** Pure restyling, no correctness value; 114 mechanical edits across serving code at close-out would hide real changes in review. |
| `B008` function-call-in-default-argument | 75 | **Ignored in `ruff.toml`, with reason.** Every hit is FastAPI's `Depends()`/`Query()` idiom. A false positive across the board, not a suppressed finding. |
| `E501` line-too-long | 34 → 5 | Line length set to 140 (this codebase uses long explanatory comments deliberately); the remaining 5 were wrapped. |
| `I001` unsorted imports | 26 | Auto-fixed. |
| `F541` f-string without placeholders | 11 | Auto-fixed. |
| `E701` multiple statements on one line | 7 | Fixed by hand — deliberate column-aligned blocks, but the rule is standard and it was 7 lines. |
| `SIM105`/`C408`/`C416`/`SIM118` | 10 | Auto-fixed (semantically equivalent). |
| `B904` raise-without-`from` | 4 | Fixed. Auth uses `from None` deliberately so the underlying JWT error never reaches the client; the rest use `from exc`. |
| `B905` `zip()` without `strict=` | 2 | Fixed as `strict=True`. In `explain.py` this is a genuine guard: a feature/SHAP length mismatch is exactly the 10-vs-11-feature bug this project already hit. |
| `SIM108` if-else vs ternary | 1 | `# noqa` with reason — the ternary is a 150-char line. |

Current state: **`ruff check` reports `All checks passed!`**, and frontend eslint reports 0 errors and 0 warnings across 23 files.

**Type-checking (mypy) was not added — a deliberate scope decision, not an oversight.** This is a capstone at close-out. `main.py` alone is ~3,200 lines of largely un-annotated FastAPI handlers plus pandas code, where mypy is weakest; a meaningful run would mean either hundreds of errors or a config permissive enough to prove nothing. Adding it as a non-blocking, always-red check would be worse than not having it. It is a real gap, stated as one.

**Prettier was not added either.** eslint (via CRA's `react-app` config) already runs clean and catches correctness issues; prettier would reformat all 23 source files for style alone.

### Dependency pinning is a standing practice, not a one-off fix

**Every dependency is pinned to an exact version. A version bump is a deliberate, tested change, never an implicit one.**

Audit results at the time this was written:

- **`backend/requirements.txt`: already 100% exact** — every line uses `==`, zero loose specifiers.
- **`frontend/package.json`: 10 of 11 dependencies were loose** (caret ranges like `^1.7.7`). All 10 are now pinned exactly — **to the versions actually installed and passing tests**, read from the lock file and the running container, not to whatever the range happened to resolve to.
- **`package-lock.json` was itself out of sync** and `npm ci` refused to run against it (`Missing: yaml@2.9.0 from lock file`). Regenerated; `npm ci` now installs 893 packages cleanly, and all 11 direct dependencies match `package.json` exactly.
- **`frontend/Dockerfile.dev` used `npm install`, now `npm ci`.** `npm install` can silently resolve a newer version and rewrite the lock during an image build — the same class of drift as the shap incident, in the other half of the stack.

## Documentation Practices

This project has hit closely-related failure modes six times in one session. They are not all the same failure, and the distinction matters — the later ones are worse than the earlier ones.

**Category A — a claim that was true when written and went stale.** The underlying code or data changed and the documentation stood uncorrected until something forced a re-check. Instances 1 and 3 below.

**Category B — a claim that was never true when it was made.** Not decay; the claim was written without checking. Instances 2 and 5 below.

**Category C — verification performed against an environment that had silently diverged from its own source of truth.** The most serious mode, because the claim looks *independently verified* — a real command was really run and really passed — while the thing it was run against was not the project. Instance 6 below. Categories A and B corrupt a statement; category C corrupts the evidence used to check statements, including evidence for unrelated claims.

1. A file-tree entry claimed `test_smoke.py` had "11 backend tests" — actually 21, across two files, by the time it was checked. *(A)*
2. `README.md` asserted `LecturerAIInsights.jsx` "exists... but is not imported or referenced anywhere in App.js" — the file had already been deleted (commit `5fd48d8`, before this session began), and its deletion was already documented in `CHANGELOG.md`. The claim was never true at any point during this session; it was written without checking the filesystem first. *(B)*
3. `model_card.md`/`README.md` cited the live model's fail-class recall (`0.8374`) as current performance without qualification, after a data refresh had already corrected 205 real students' labels and measurably changed what that number means — see the recall-gap finding above. *(A)*
4. A prediction outage sat behind 21 green tests for several rounds while being reported as "verified live" — the suite exercised `/api/predict` but never the roster path (see [Testing Practices](#testing-practices--a-real-outage-the-suite-missed) above). "Tests pass" is only evidence for what the tests actually execute.
5. A fix was reported as applied and was never on disk (see [Source-control note](#source-control-note--a-claimed-fix-that-was-never-on-disk) above) — reported-done is not the same as verified-present. *(B)*
6. Every test result across a session was produced by a hand-patched container that no clean checkout could reproduce (see [Container drift](#container-drift--the-verification-environment-was-not-the-project) above). *(C)*

**Going forward: any numeric claim in `README.md` or `model_card.md` (test counts, row counts, recall/precision/F1 figures, file-existence claims) should be regenerated from a live command at the moment the documentation is written or updated — `pytest --collect-only`, `git log`/`git cat-file -e`, a real script run against current data — never hand-typed or carried forward from a previous version of the document without re-verification.** A number that was true when written is not the same guarantee as a number that's true now; this project's own history in this section is the evidence for why that distinction matters.

**And for category C specifically: regenerating a number from a live command is only as trustworthy as the environment the command ran in.** Where a claim rests on a container, the container should be one that was recently built from the repo — otherwise the freshly-generated number is a fact about a local machine, not about this project.

---

## Authors

- **Sangam Ghale Gurung** — Full-stack development, ML pipeline, AI integration

King's Own Institute · Bachelor of Information Technology · Capstone Project 1 · 2026

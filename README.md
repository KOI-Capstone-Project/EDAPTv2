# EDAPT v2 — Educational Data Analytics and Predictive Tool

> King's Own Institute (KOI) — Capstone Project (Second Year)

EDAPT v2 is a role-based academic analytics platform. It predicts whether a student will pass or fail a subject from their recorded assessment marks — both once a subject is complete and, separately, from genuinely mid-semester partial records — and surfaces those predictions, along with real per-feature explanations, through role-scoped dashboards, an assessment-record explorer, and a roster-first predictor tool.

> **Note on repository state**: this README describes what is in the working tree right now, on branch `sangam_dev`. A substantial amount of what's documented below — the data-reliability fix, current ML pipeline, automated retraining infrastructure, outcome reconciliation, fairness auditing, SHAP explainability, and the frontend page merges — is **not yet committed or pushed to `main`**. If you're reading this from `main`, expect an older version of the system.

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
│   │       ├── evaluate_thresholds.py           # Test-set threshold sweep (superseded by validate_threshold.py)
│   │       ├── validate_threshold.py            # Honest, validation-split threshold selection
│   │       ├── reconcile_predictions.py         # Backfills actual_pass against real outcomes
│   │       ├── prediction_accuracy_report.py    # Predicted-vs-actual accuracy report
│   │       ├── check_bias_persistence.py        # Cross-retrain fairness-flag trend detection
│   │       ├── verify_dynamic_period_e2e.py     # Isolated end-to-end test of dynamic period resolution
│   │       ├── investigate_fail_rate_shift.py   # Diagnostic: period-over-period fail-rate investigation
│   │       ├── best_model_simulated_progress.pkl  # Simulated-progress model artifact (not in the registry)
│   │       └── models/
│   │           ├── registry.json                # Version metadata, live pointer, promotion history
│   │           └── model_<timestamp>.pkl         # One file per registered version
│   ├── scripts/
│   │   └── retrain_loop.sh            # Sidecar scheduler loop (scheduled_retrain.py → sleep 24h → repeat)
│   ├── tests/
│   │   └── test_smoke.py              # 11 backend tests
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
│   ├── Capstone_data_20260324.csv     # Raw source data
│   ├── subject_reliability.json       # fully_clean / mostly_clean / unreliable classification
│   └── subject_reliability_report.csv
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
- A `.env` file in the project root (see [Environment Variables](#environment-variables) — there is currently no `.env.example` checked into the repo to copy from, despite `.gitignore` expecting one; create `.env` directly using the variable names below)

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

Three demo accounts are seeded automatically on first backend startup if the `users` table is empty (`_seed_default_users()` in `main.py`):

| Email | Password | Role | Super-admin |
|-------|----------|------|--------------|
| `admin` | `Admin@2025!` | Head of Technology | Yes |
| `hos` | `HoS@2025!` | Head of School | No |
| `user` | `Lect@2025!` | Lecturer (assigned `ICT104`, `ICT201`, `ICT301`) | No |

Use **User Management** (`/users`, super-admin only) to create additional accounts.

---

## Loading Data

The raw dataset (`data/Capstone_data_20260324.csv`) is loaded automatically into an in-memory pandas DataFrame **at backend startup** — this is the primary path, not a manual step. `POST /api/ingest` also still exists as a runtime override (upload a different CSV/XLSX without restarting the container), matching the original **Data Ingestion** page's behavior, but it's a secondary path now, not the only way data gets in.

### Expected Columns

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

Confirmed directly from `backend/app/ml/models/registry.json` (`live_version: 20260715_132655`):

| | Value |
|---|---|
| Subjects trained on | 124 (`fully_clean` + `mostly_clean` per `data/subject_reliability.json`, `TSL713` excluded) |
| Training row count | 58,267 |
| Trained on | All periods before 25.3, excluding the 23.1 pilot period |
| Validated on | 25.3 |
| Accuracy | 0.9502 |
| Fail-class precision / recall / F1 | 0.7695 / 0.8374 / 0.8020 |
| Decision threshold | 0.50 (chosen via a held-out validation split, not by sweeping the test set directly — see `validate_threshold.py`) |

### Model card, ablation study, and a real calibration finding

Full detail in [`model_card.md`](model_card.md) — three rounds of real, evidence-based validation, including two places where an earlier round's own conclusion was corrected after a fairer test rather than left standing. Headlines:

- **Ensemble vs. single XGBoost**: an apples-to-apples comparison (both WITH SMOTE, isolating architecture as the only variable) found the ensemble's ranking-quality edge is not a real, repeatable gain (~0.2pp PR-AUC — smaller than this project's own established noise threshold). What *is* real: at the shared 0.50 threshold, the ensemble trades ~5 points of fail-class precision for a **+3.53 percentage-point fail-class recall gain** over a single XGBoost — confirmed to replicate almost exactly (+3.53pp vs. +3.53pp) on a second, independently-built validation period. The ensemble is kept for that recall advantage specifically — an explicit, quantified, non-performance-purity reason, not an assumed one.
- **SMOTE vs. class-weighting — a Round 1 finding that didn't hold up and was corrected, not left standing.** Round 1 claimed removing SMOTE collapses fail-class precision from 0.72 to 0.48; Round 2 found that comparison judged the no-SMOTE model at a threshold tuned for a *different* model's probability distribution. Given its own honestly re-validated threshold, the no-SMOTE model reaches precision 0.686 / recall 0.819 — close to the SMOTE model's 0.724 / 0.799, with marginally *higher* raw ranking metrics. Current position: neither SMOTE nor the ensemble has a demonstrated fair performance advantage — both are kept as reasonable working defaults, not as provably-best choices.
- **Dumb baseline check**: a trivial "flag if average score to date < 50%" rule with zero ML gets within ~1 percentage point of the full model's PR-AUC. The model's real value is a smooth, well-positioned probability and a usable precision/recall tradeoff — not a large raw ranking-quality gain over the obvious signal.
- **A real calibration problem, and a real bug it helped surface**: the model ranks students correctly (ROC-AUC 0.974) but its raw predicted probabilities understate true pass likelihood by roughly 15–30 percentage points across the entire 10–90% predicted range — only the two extreme bands (~78% of students) are well-calibrated. This calibration gap turned out to be the root cause of a real, reported production bug — see [Mid-semester (partial-progress) prediction](#mid-semester-partial-progress-prediction) below — fixed there, not fixed here (the underlying miscalibration itself is still open, tracked as a follow-up for Platt scaling / isotonic regression).
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

A **separate** model, `best_model_simulated_progress.pkl`, trained on synthetic partial-progress snapshots constructed from real, fully-graded enrolments (`train_simulated_progress.py` / `build_simulated_progress_features()`) — necessary because the real dataset is a closed, historical snapshot with no genuine partial records; an earlier attempt to reuse the complete-record model's feature definition on partial data produced 1.0000 accuracy, which was correctly diagnosed as target leakage rather than reported as a result. Not entered into the versioned registry (`"deployed": false` in its own metadata) — a distinct model family by design.

```bash
docker exec edaptv2_backend python3 -m app.ml.train_simulated_progress
```

Serving routes on coverage, computed server-side and never trusted from the client:

| Coverage | Tier | Model | API response |
|---|---|---|---|
| ≥ 99.5% | complete | `predict()`, live registry model | `estimate_type: null` |
| 50–99.5% | partial | `predict_partial()`, simulated-progress model, threshold 0.25 | `estimate_type: "mid-term estimate"` |
| < 50% | insufficient | none called | `coverage_status: "insufficient_data"`, prediction fields `null` |

**A real, reported production bug was found and fixed here**: a screenshot showed a mid-term prediction displaying 73.1% (green "Safe" badge) directly above the plain-text label "Fail" for the same prediction. Root cause: `predict()` and `predict_partial()` use different, independently and honestly validated decision thresholds (0.50 vs. 0.25 respectively), but the risk band (Safe / At Risk / High Risk) used to be one hardcoded 65%/40% split shared by both — since the mid-term threshold implies a Pass/Fail boundary at 75% (`100 × (1 − 0.25)`), which sits *above* the shared 65% Safe floor, any probability in 65–75% could be "Fail" by the label and "Safe" by the band simultaneously. Reproduced the exact reported case live, then fixed it at the shared source (`predictor.py`'s `_compute_risk_band()`, used by both prediction functions) rather than patching the frontend — the Safe floor is now derived from whichever threshold actually produced the label (`max(65, 100 × (1 − threshold))`), making the contradiction structurally impossible rather than just less likely. The mid-term model's honestly-validated 0.25 threshold was deliberately **not** changed to 0.50 to fix this — that would have silently discarded real validation work and reduced mid-term fail-detection recall. Two regression tests cover this (an HTTP-level reproduction and a pure unit-level sweep across five threshold values).

One direct, visible consequence: **mid-term predictions now show a different risk-scale legend than complete-record predictions** (`0–39 / 40–74 / 75–100` vs. `0–39 / 40–64 / 65–100`) — the same raw percentage can land in a different band depending on which model produced it. This is surfaced to the user, not just documented: the Predictor page shows a plain-language caption above the risk scale whenever a mid-term estimate is displayed, explaining that the two models' percentages aren't yet on the same scale. This is a **display-level fix for a deeper, still-open root cause** — the mid-term model's calibration gap (see the calibration finding above) — not a resolution of it; `model_card.md`'s Known Limitations has the full connection and flags re-testing whether the two scales could be unified once that calibration work is done.

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

**13 tests, all passing** as of this README (confirmed live, not assumed) — covering health/auth, the three coverage-tier prediction paths, server-side recomputation of partial scores (regression test for the train/serve consistency bug), SHAP explanation consistency for both models, and the Fail/Safe risk-band contradiction fix (both an HTTP-level reproduction of the reported bug and a pure unit-level invariant sweep across five threshold values).

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
| `main` | Stable, reviewed code |
| `sangam_dev` | Active development — **currently ahead of `main` by all of the work described in this README** |

PRs are opened from `sangam_dev` → `main`.

---

## Known Open Items

Stated plainly rather than rounded up or omitted:

- **Gemini drift verification is blocked**, not resolved — whether Gemini's generated text stays grounded in the real SHAP numbers it's fed has never been tested against a live model, since no real `GEMINI_API_KEY` exists in this environment.
- **The age 0–20 fairness finding is a single observation**, not a confirmed trend (see [Fairness / bias auditing](#fairness--bias-auditing)).
- **Predicted probabilities are meaningfully miscalibrated in the 10–90% range** (see [model card](model_card.md)) — ranking is correct, the displayed percentage isn't literally trustworthy outside the two extreme bands. No calibration correction has been applied yet. This is also the confirmed root cause of the Fail/Safe UI bug (fixed at the display level — see [Mid-semester prediction](#mid-semester-partial-progress-prediction) — but not at the root).
- **Once the mid-term model's calibration is corrected (Platt/isotonic, still unimplemented), re-check whether the two risk-band scales can be unified back into one.** They currently differ (Safe at 65% for complete records, 75% for mid-term) specifically because the two models' probabilities don't mean the same thing at the same number — fixing that root cause might remove the need for two scales, but that should be re-tested against real data when calibration work happens, not assumed.
- **`build_target()` has a real, currently-harmless latent bug**: no `ATTEMPTNUMBER` filtering, so a same-assessment-type resit within an already-"clean" enrolment would be double-counted. Verified this affects 0 real rows today (an unrelated existing filter happens to exclude every case where it could occur), but it's not a guaranteed protection for future data. Not fixed — needs a deliberate decision on training-target logic.
- **No `.env.example` exists** in the repo despite `.gitignore` expecting one — `.env` must be created directly from the variable names documented above.
- **The prod scheduler sidecar was verified in isolation** (image build, non-root permissions, error-resilience), not against the full running prod stack (nginx/frontend-prod alongside it).
- **This entire feature set is uncommitted** on `sangam_dev` relative to `main` — see the note at the top of this file.

---

## Authors

- **Sangam Ghale Gurung** — Full-stack development, ML pipeline, AI integration

King's Own Institute · Bachelor of Information Technology · Capstone Project 1 · 2026

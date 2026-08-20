# EDAPTv2 — QA Test Plan

**Project:** EDAPTv2 (Student Performance Prediction & Early Intervention Platform)
**Prepared:** 2026-08-20
**Scope:** Backend API (FastAPI), Frontend (React), ML pipeline, Data ingestion

---

## 1. Objective

Verify that EDAPTv2's authentication, role-based access control, data ingestion, dashboards, predictions, and admin features work correctly, securely, and consistently across roles before release.

## 2. In Scope

- REST API endpoints in `backend/app/main.py`
- Role-based access control (Lecturer, Head of School, Head of Technology, Super Admin)
- Data ingestion pipelines (capstone + attendance)
- ML prediction, explanation (SHAP), and model health reporting
- Public API key management console (new feature)
- Frontend pages under `frontend/src/pages/`
- Regression coverage of existing automated tests

## 3. Out of Scope

- Load/performance testing (unless separately requested)
- Third-party Gemini API correctness (only integration/error-handling tested here)
- Infrastructure/CI pipeline itself

## 4. Test Environment

| Item | Details |
|---|---|
| Backend | `backend/` — FastAPI, run via `docker-compose.yml` or `uvicorn` |
| Frontend | `frontend/` — React app |
| Config | Copy `.env.example` → `.env` (never use real secrets in shared `.env`) |
| Test data | `data/subject_reliability.json`, `data/subject_reliability_report.csv`, synthetic data via `scripts/generate_synthetic_data.py` |
| Existing automated tests | `backend/tests/test_smoke.py`, `backend/tests/test_ingestion_e2e.py`, `frontend/src/pages/PredictorView.test.jsx` |

## 5. Roles Under Test

| Role | Expected Access |
|---|---|
| Lecturer | Own class/subject data only (row-level filtered) |
| Head of School | All data, ingestion, dashboards — no user/admin management |
| Head of Technology | Everything Head of School has + user management, API keys, model health |
| Super Admin (`is_super_admin=True`) | Reserved system-administrator-only actions |
| External API caller (API key) | `/api/v1/predict` only, no session access |

---

## 6. Test Areas & Cases

### 6.1 Authentication (`/api/auth/*`)

| # | Test Case | Steps | Expected Result |
|---|---|---|---|
| A1 | Valid login | POST `/api/auth/login` with correct credentials for each role | 200, JWT returned, `role` field correct |
| A2 | Invalid login | Wrong password / unknown email | 401, no token issued |
| A3 | Forgot password | POST `/api/auth/forgot-password` with valid/invalid email | Valid: reset flow triggered; invalid: no user enumeration leak |
| A4 | Reset password | POST `/api/auth/reset-password` with valid/expired/reused token | Valid token succeeds once; expired/reused rejected |
| A5 | Change password | Logged-in user changes password with correct/incorrect current password | Correct: success; incorrect: 401/403, old password still works |
| A6 | Logout | POST `/api/auth/logout` | Token invalidated / session cleared |
| A7 | Update profile | POST `/api/auth/update-profile` with valid/invalid fields | Valid: persists; invalid (e.g. bad email format): rejected |
| A8 | Access without token | Call any protected endpoint with no `Authorization` header | 401 |
| A9 | Expired/malformed JWT | Call protected endpoint with tampered/expired token | 401 |

### 6.2 Role-Based Access Control

| # | Test Case | Expected Result |
|---|---|---|
| R1 | Lecturer calls ingestion endpoints (`/api/ingest/*`) | 403 — Head of School+ only |
| R2 | Lecturer views `/api/data`, `/api/summary`, `/api/dashboard/*` | Data returned filtered to own class/subject only |
| R3 | Head of School views same endpoints | Full dataset returned, no filtering |
| R4 | Non-admin (Lecturer/Head of School) calls `/api/users`, `/api/api-keys` | 403 — Head of Technology only |
| R5 | Head of Technology calls admin endpoints | 200, full access |
| R6 | Super-admin-only action attempted by Head of Technology (non-super-admin) | 403 |
| R7 | Cross-role data leak check | Confirm Lecturer never receives another lecturer's students in any response payload |

### 6.3 Data Ingestion (`/api/ingest/*`)

**Note:** confirm is asynchronous — `POST /api/ingest/{kind}/confirm` returns **202** immediately with `{job_id, status: "running"}`, not the finished result. The actual parse/feature-build/retrain-check/commit work runs in the background (`IngestJob` in `app/db/models.py`); poll `GET /api/ingest/jobs/{job_id}` (or `GET /api/ingest/jobs` for the full list) until `status` is `success` or `failed`, then assert on `result/error_detail`.

| # | Test Case | Steps | Expected Result |
|---|---|---|---|
| I1 | Capstone data analyze | POST `/api/ingest/capstone/analyze` with valid file | Returns column classification / preview correctly |
| I2 | Capstone data confirm | POST `/api/ingest/capstone/confirm` after analyze, then poll `GET /api/ingest/jobs/{job_id}` | Confirm returns 202 + job_id immediately; job eventually reaches `status: "success"`, data committed and appears in `/api/data` |
| I3 | Attendance analyze/confirm | Same flow via `/api/ingest/attendance/analyze` + `/confirm`, then poll the job | Job reaches `success`; attendance data ingested correctly |
| I4 | Column decision override | POST `/api/ingest/columns/decide` with manual column type overrides | Overrides respected in final ingested schema |
| I5 | Malformed file upload | Upload corrupt/wrong-format file | Graceful 4xx error, no server crash, no partial data committed |
| I6 | Duplicate ingestion | Re-ingest same file/period | Either rejected or correctly deduplicated (confirm expected behavior with dev) |
| I7 | Ingest preview endpoints | GET `/api/ingest/preview`, `/api/ingest/attendance/preview` | Preview matches what was actually committed |
| I8 | Non-privileged role attempts ingestion | Lecturer calls any `/api/ingest/*` | 403 |
| I9 | Confirm token re-use | Call confirm twice with the same token | First call 202s and starts a job; second call 404s ("no matching pending upload") since the token is consumed the moment it's accepted, not when the job finishes |
| I10 | Job failure surfaced | Force a confirm job to fail (e.g. malformed stored bytes) | Job reaches `status: "failed"` with a populated `error_detail`; UI shows it in the Ingestion Activity panel, not a silent hang |
| I11 | Jobs list endpoint | GET `/api/ingest/jobs` as Head of School/Technology | Returns recent jobs across all admins, most recent first, regardless of who started them |
| I12 | Non-privileged role reads jobs | Lecturer calls `/api/ingest/jobs` or `/api/ingest/jobs/{id}` | 403 |
| I13 | Sidebar notification badge | Confirm an ingestion, wait for it to finish, without visiting Data Ingestion | Sidebar's "Data Ingestion" nav item shows a numeric badge (red if any finished job failed) |
| I14 | Badge clears on visit | Navigate to Data Ingestion page after a badge appears | Badge clears immediately (localStorage last-seen-job-id updates); Ingestion Activity panel lists the job with correct status/result |
| I15 | Resume after refresh | Analyze (but don't confirm) a file, then refresh the page | Upload card shows a "Resumed …" banner with the same file info, no re-upload required, within the 30-minute pending-upload TTL |

### 6.4 Dashboards (`/api/dashboard/*`, `/api/explorer/*`, `/api/subjects/*`)

| # | Test Case | Expected Result |
|---|---|---|
| D1 | Each of 8 dashboard endpoints returns correct data for valid filters (subject, trimester, year, classgroup) | Correct aggregation, matches source data |
| D2 | Invalid/nonexistent filter values (e.g. bad subject name) | Empty result or clear 4xx, not a 500 |
| D3 | Explorer records + filters (`/api/explorer/records`, `/filters`) | Pagination and filtering behave correctly |
| D4 | Explorer student detail (`/api/explorer/student/{student_id}`) | Valid ID returns record; invalid ID returns 404 |
| D5 | Explorer export (`/api/explorer/export`) | Exported file matches on-screen filtered data |
| D6 | Subject list/assessments/roster/analytics endpoints | Correct data per subject, role-filtered where applicable |
| D7 | Role filtering applied consistently across all dashboard/explorer endpoints | Lecturer never sees other classes' data in any of these |

### 6.5 ML Prediction & Explainability

| # | Test Case | Expected Result |
|---|---|---|
| M1 | POST `/api/predict` with valid student data | Returns prediction + SHAP explanation, response schema correct |
| M2 | POST `/api/predict` with missing/invalid fields | 422 with clear validation error |
| M3 | POST `/api/v1/predict` (public API) with valid API key | 200, prediction returned |
| M4 | POST `/api/v1/predict` with missing/invalid/revoked API key | 401 |
| M5 | POST `/api/v1/predict` with valid key but malformed payload | 422/400, not 500 |
| M6 | Model health endpoint `/api/admin/model-health` | Accurate current model version, metrics, last retrain time |
| M7 | Compare-and-promote / threshold validation logic (`compare_and_promote.py`, `validate_threshold.py`) | New model only promoted if it passes accuracy/bias thresholds — verify with a deliberately worse model in a test/staging run |
| M8 | Bias persistence check (`check_bias_persistence.py`) | Flags/blocks promotion if bias regresses across protected groups |
| M9 | Prediction reconciliation report (`reconcile_predictions.py`, `prediction_accuracy_report.py`) | Report numbers match manual spot-check against actual outcomes |

### 6.6 API Key Management Console (new feature)

| # | Test Case | Steps | Expected Result |
|---|---|---|---|
| K1 | Create API key | POST `/api/api-keys` as Head of Technology | 201, key returned once, shown only at creation |
| K2 | List API keys | GET `/api/api-keys` | Keys listed with metadata, hashed key never exposed |
| K3 | Revoke API key | DELETE `/api/api-keys/{key_id}` | Key marked revoked; subsequent `/api/v1/predict` calls with it get 401 |
| K4 | Usage stats | GET `/api/api-keys/usage` | `last_used_at` updates correctly after use, counts accurate |
| K5 | Non-admin access | Lecturer/Head of School attempts any `/api/api-keys/*` call | 403 |
| K6 | Frontend ApiConsole page | Create/list/revoke via UI (`frontend/src/pages/ApiConsole.jsx`) | UI reflects backend state correctly, error states handled |
| K7 | Revoked key reuse | Attempt external prediction call with a revoked key | 401, no prediction leaked |

### 6.7 Admin — Users & Audit

| # | Test Case | Expected Result |
|---|---|---|
| U1 | List/create/update/delete users (`/api/users`) as Head of Technology | CRUD works correctly, validation on bad input |
| U2 | Same actions attempted by non-admin | 403 |
| U3 | Audit log endpoint (`/api/audit-logs`) | Login, ingestion, user changes, key creation/revocation all produce audit entries |
| U4 | Audit log immutability | No endpoint allows editing/deleting existing audit entries |

### 6.8 Interventions

| # | Test Case | Expected Result |
|---|---|---|
| V1 | Create intervention (`POST /api/interventions`) | 201, persisted correctly |
| V2 | List interventions (`GET /api/interventions`) | Filtered correctly per role |
| V3 | Action types list (`/api/interventions/action-types`) | Returns valid, complete set |
| V4 | Intervention outcome report (`intervention_outcome_report.py`) | Outcomes correctly linked to interventions and predictions |

### 6.9 Gemini AI Integration

| # | Test Case | Expected Result |
|---|---|---|
| G1 | Alert/analyse/ask endpoints (institution + subject level) | Valid responses for normal input |
| G2 | Gemini API failure/timeout simulated | Graceful error to frontend (`AIChatbox.jsx`, `GeminiPanel.jsx`), no crash |
| G3 | Token log (`/api/gemini/token-log`) | Usage logged accurately |

### 6.10 Frontend (manual + `PredictorView.test.jsx` as reference)

| # | Test Case | Expected Result |
|---|---|---|
| F1 | Login / ForgotPassword flow | Correct redirects, error messages for bad input |
| F2 | Role-based navigation (Sidebar/Layout) | Lecturer vs Head of School vs Head of Technology see different menu items |
| F3 | AdminDashboard, LecturerDashboard render correctly per role | Data matches backend, no console errors |
| F4 | DataIngestion page full flow | Upload → preview → column decisions → confirm, matches backend behavior (6.3) |
| F5 | PredictorView | Prediction request/response render correctly, loading/error states work |
| F6 | ExplorerView, SubjectAnalytics | Filtering, pagination, export button work |
| F7 | ModelHealth page | Displays current model metrics accurately |
| F8 | UserManagement, ApiConsole, SettingsView | Admin-only visibility enforced in UI, not just API |
| F9 | AuditLog page | Displays entries, filterable |
| F10 | ErrorBoundary | Simulate a component crash — fallback UI shown, no blank screen |

---

## 7. Regression Checklist

- [ ] Run `backend/tests/test_smoke.py` and `test_ingestion_e2e.py` — all pass
- [ ] Run `frontend/src/pages/PredictorView.test.jsx` — passes
- [ ] Re-verify all endpoints listed in `.github/workflows/ci.yml` pass in CI before merge
- [ ] Confirm no new endpoint is missing an auth/role dependency (`Depends(get_current_user | require_head_of_school | require_admin | require_super_admin | require_api_key)`)

## 8. Security Spot-Checks

- [ ] SQL/NoSQL injection attempts on filter/query params (subject, trimester, classgroup, student_id)
- [ ] JWT tampering (role field modified client-side) rejected server-side
- [ ] API keys stored hashed (SHA-256), never returned in list/usage endpoints
- [ ] File upload endpoints reject oversized/executable/malicious files
- [ ] `.env` values never exposed via any API response or error message

## 9. Defect Reporting

Log defects with: endpoint/page, role used, steps to reproduce, expected vs actual result, request/response payload (redact any secrets), severity (Blocker/Critical/Major/Minor).

## 10. Sign-off Criteria

- All Blocker/Critical defects resolved
- 100% of role-based access control cases (6.2) pass
- All automated regression tests green
- No secrets/PII exposed in any tested response

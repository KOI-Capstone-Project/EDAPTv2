# Changelog

All notable changes to EDAPT v2 are documented here.

---

## [Unreleased] — 2026-05-08

### Added

#### Frontend — Pages (full implementations)
- **`SubjectAnalytics.jsx`** (`/subject-analytics`) — complete rebuild from placeholder; Subject A + optional Subject B selectors for side-by-side comparison; trimester filter; KPI cards (avg mark, pass rate, failure rate, student count) vs institution benchmarks; grade distribution grouped bar chart (subject vs subject vs institution); performance trend line chart (all periods); assessment type breakdown horizontal bar; period-by-period comparison bar chart for single-subject view; difficulty badge (Low / Medium / High); delta arrows showing change vs previous period
- **`AdminExplorer.jsx`** (`/student-analytics`) — complete rebuild from placeholder; multi-filter bar (search by student ID, subject, trimester, country, gender, pass/fail); paginated table (50 rows per page) with colour-coded marks and pass/fail badges; "View" button on each row opens a sticky student detail panel; detail panel shows avg mark KPI, overall pass badge, performance trend line chart, and peer comparison bar chart (student avg vs class avg vs institution avg); pagination controls
- **`AdminPredictor.jsx`** (`/predictive-reports`) — complete rebuild from placeholder; subject selector (populated from `/api/subjects/list`); Assessment 1 mark input (required) and Assessment 2 mark input (optional, uses backend median when blank); SVG semicircle arc gauge showing pass probability %; risk badge (Safe / At Risk / High Risk) with colour coding; Gemini one-sentence advice box; model name and accuracy shown in page header (admin-only data from `/api/predict`); risk scale legend; in-memory recent predictions history table (last 10 runs)
- **`LecturerAIInsights.jsx`** (`/ai-insights`) — complete rebuild from placeholder; scope selectors (subject + trimester) populated from `/api/explorer/filters`; scope summary line updates live; suggested question chips for quick prompting; embeds `GeminiPanel` component which auto-alerts on scope change, supports deep analysis on demand, and provides 3-message rolling Q&A; AI disclaimer footer

#### Documentation
- **`README.md`** — complete rewrite reflecting v2 architecture: accurate tech stack (FastAPI + in-memory pandas, no PostgreSQL/Docker dependency); both roles documented (Lecturer / Head of Technology / super-admin); all current routes with descriptions; up-to-date project file structure; two-terminal quick start (no Docker required); default login credentials; data ingestion column guide; ML model training instructions; Gemini AI tiers explained; full API endpoint reference; branch strategy

---

## [2026-05-08] — UI Improvements and Data Ingestion Fixes

### Added

#### Frontend
- **`PageUnavailable.jsx`** (`frontend/src/components/`) — shared "coming soon" component with `role` prop; back button navigates to `/dashboard/admin` for admins or `/dashboard/lecturer` for lecturers; replaces duplicated `UnavailablePage` that was previously defined inline in five separate files
- **`AdminSettings.jsx`** (`/settings` for admin role) — account settings page for Head of Technology; displays name, email, role; change password section calling `POST /api/auth/change-password`
- **`LecturerAIInsights.jsx`** (`/ai-insights`) — initial placeholder page (upgraded to full implementation in current session)
- Dataset file `data/Capstone_data_20260324.csv` added to repository for development use

#### Backend (`backend/app/main.py`)
- `DELETE /api/users/{email}` — delete a staff account; requires super-admin; guards prevent deleting the `admin` system account or the calling user's own account; writes audit event on success
- `is_super_admin` field — added to the `USERS` dict, JWT token payload, and user response object; `True` only for the `admin` email; controls access to Audit Log and User Management
- `POST /api/gemini/institution-alert` — institution-wide Gemini alert for the Head of Technology; summarises subjects below 50% pass rate and top 3 failing subjects in one sentence
- `POST /api/gemini/institution-analyse` — institution-wide 4–5 sentence deep analysis with exact numbers and two recommended actions
- `POST /api/gemini/institution-ask` — institution-wide Q&A using full institution stats as context
- `GET /api/gemini/token-log` — returns per-request Gemini API token usage log (admin only)
- `require_super_admin` dependency — FastAPI dependency that raises `403` unless the authenticated user has `is_super_admin: true`; used on Audit Log and User Management endpoints

### Changed

#### Frontend
- **`Sidebar.jsx`** — added AI Insights (`/ai-insights`) to `LECTURER_NAV`; moved Audit Log from `ADMIN_NAV_BASE` to `ADMIN_NAV_SUPER` so only the super-admin (`admin` email) sees it; `ADMIN_NAV_SUPER` changed to an array (`[AuditLog, UserManagement]`) with spread syntax in navItems computation; added AI star SVG icon
- **`DataIngestion.jsx`** — `fetchPreview` rewritten as a plain `async` function (was `useCallback`) defined before `handleProcess` to avoid ordering issues; `handleProcess` now `await`s `fetchPreview(1)` so the preview table updates after upload completes; added `useEffect` to auto-call `fetchPreview(1)` on mount so existing data is shown immediately; added `previewError` state with error banner; table CSS set to `minWidth: '100%', width: 'max-content'` for proper horizontal scroll; preview condition changed to `previewData.length > 0`; restored `useCallback` to React import (required by `pickFile`)
- **`UserManagement.jsx`** — added `handleDelete` function with `window.confirm` dialog; delete calls `DELETE /api/users/:email`, filters user from local state on success, and cancels any active inline edit for the deleted user; added delete button (red background, trash icon) to each table row's actions column
- **`AuditLog.jsx`** — updated to use the revised backend endpoint with `is_super_admin` guard
- **`App.js`** — added `LecturerAIInsights` import and `/ai-insights` route under `Protected`; added `AdminSettings` and `LecturerSettings` routes; `SettingsPage` component renders the correct settings page based on role

#### Backend (`backend/app/main.py`)
- `_DATA` initialised as `pd.DataFrame()` instead of `None` — allows `.empty` check everywhere without `None` guard; `GET /api/ingest/preview` updated to check `_DATA is None or _DATA.empty`
- `GET /api/ingest/preview` — added `global _DATA` declaration so the in-memory DataFrame is read correctly after upload; previously returned empty data even after a successful ingest

### Fixed
- **DataIngestion preview after upload** — `fetchPreview` was called without `await` inside `handleProcess` (fire-and-forget), so the table always showed stale/empty data; fixed with `await fetchPreview(1)`
- **DataIngestion `useCallback` import** — previous session removed `useCallback` from the React import while `pickFile` still used it; restored to fix `ReferenceError: useCallback is not defined`
- **Super-admin gate on Audit Log and User Management** — both pages were visible to all `Head of Technology` accounts; now gated to `admin` email only via `require_super_admin` backend dependency and sidebar conditional

---

## [2026-05-06] — Role-Based Dashboards, Explorer, Predictor, and Gemini Integration

### Added

#### Frontend — Pages
- **`Login.jsx`** — rewritten in JSX; role-based redirect on success (`/dashboard/admin` for Head of Technology, `/dashboard/lecturer` for Lecturer); clears registration state on mount; password visibility toggle; error banner
- **`AdminDashboard.jsx`** (`/dashboard/admin`) — institution-wide analytics for the Head of Technology; KPI cards (total students, avg mark, pass rate, at-risk count) with period-over-period delta badges; six chart panels: grade distribution bar, pass/fail donut, performance trend line, assessment comparison bar, international performance bar, difficulty index bar; year/trimester/subject/classgroup filter controls; institution-level Gemini alert panel; `ErrorBoundary` wrapper
- **`LecturerDashboard.jsx`** (`/dashboard/lecturer`) — per-lecturer view filtered to assigned subjects; KPI cards with delta badges; grade distribution, pass/fail donut, performance trend, assessment comparison, international split charts; `GeminiPanel` at the bottom for subject-level AI alerts, full analysis, and free Q&A
- **`LecturerExplorer.jsx`** (`/explorer`) — student record explorer scoped to the lecturer's assigned subjects; subject, trimester, search, and pass/fail filters; paginated results table; mark progress bars inline; sidebar student detail panel with mark timeline and peer comparison
- **`LecturerPredictor.jsx`** (`/predictor`) — ML prediction tool for lecturers; subject selector pre-populated from assigned subjects; Assessment 1 and Assessment 2 mark inputs; calls `POST /api/predict`; result card shows pass probability, risk category, and Gemini one-line advice
- **`LecturerSettings.jsx`** (`/settings`) — profile display (name, email, role, assigned subjects); change-password section calling `POST /api/auth/change-password`; notification preference toggles persisted to `localStorage`
- **`SubjectAnalytics.jsx`** (`/subject-analytics`) — initial implementation; subject and trimester dropdowns; grade distribution chart, performance trend, assessment comparison; subject summary stats; later rebuilt fully in current session
- **`UserManagement.jsx`** (`/users`) — admin CRUD for staff accounts; table of all users with role badge; inline edit form for name, role, and assigned subjects; create new user form; calls `GET / POST / PUT /api/users`
- **`AdminExplorer.jsx`** (`/student-analytics`) — initial implementation with student record table, filters, and detail panel; later rebuilt fully in current session

#### Frontend — Components
- **`GeminiPanel.jsx`** — reusable three-level AI insights panel; Level 1 auto-fetches a subject performance alert on mount and when subject/trimester changes; Level 2 renders a full deep-dive analysis on demand; Level 3 provides a rolling 3-message Q&A interface; used in LecturerDashboard, AdminDashboard, and (later) LecturerAIInsights
- **`ErrorBoundary.jsx`** — class component catching render errors in AdminDashboard and showing a recovery message

#### Frontend — Utilities & Services
- **`frontend/src/utils/auth.js`** — shared auth helpers: `getUser()`, `getToken()`, `getUserName()`, `getUserInitials()`; reads from `localStorage` keys `edapt_token` / `edapt_user`
- **`frontend/src/services/api.js`** — Axios instance with base URL and JWT request interceptor attaching `Authorization: Bearer <token>` to every request

#### Backend (`backend/app/main.py`)
- Complete rewrite of the backend to a single-file FastAPI app with in-memory data storage (no PostgreSQL)
- `POST /api/auth/login` — JWT login; returns token (8-hour expiry) and full user object including role, subjects, and is_super_admin
- `POST /api/auth/change-password` — verifies current password, updates bcrypt hash in `USERS` dict
- `POST /api/auth/update-profile` — update name and email for the authenticated user
- `POST /api/auth/logout` — client-side token removal; returns 200
- `GET /api/dashboard/summary` — KPI metrics with optional subject, trimester, year, classgroup filters; role-filtered (lecturers see only their subjects)
- `GET /api/dashboard/grade-distribution` — grade band counts (0–49, 50–59, … 90–100)
- `GET /api/dashboard/performance-trend` — avg mark by trimester for subject vs institution
- `GET /api/dashboard/assessment-comparison` — mean mark by assessment type
- `GET /api/dashboard/pass-fail` — pass and fail counts with pass rate
- `GET /api/dashboard/international` — avg mark by country (admin only)
- `GET /api/dashboard/difficulty-index` — subjects ranked by failure rate (admin only)
- `GET /api/dashboard/classgroups` — avg mark and pass rate by class group
- `GET /api/explorer/records` — paginated student records; admin sees all, lecturers see their subjects only
- `GET /api/explorer/filters` — available filter values (subjects, trimesters, countries, genders, age groups) scoped to role
- `GET /api/explorer/student/{student_id}` — full record for one student including per-period trend and peer comparison (class avg vs institution avg)
- `GET /api/explorer/export` — export filtered records as CSV download (admin only)
- `GET /api/subjects/list` — distinct subject codes (admin only)
- `GET /api/subjects/analytics` — detailed per-subject stats including grade distribution, performance trend, assessment breakdown, trimester comparison; supports optional Subject B for comparison
- `POST /api/ingest` — upload CSV or XLSX; parsed with pandas into in-memory `_DATA` DataFrame; returns row count, columns, and 10-row preview; writes audit event
- `GET /api/ingest/preview` — paginated preview of the currently loaded DataFrame
- `GET /api/audit-logs` — event history with optional filters for action type, status, and user (super-admin only)
- `GET /api/users` — list all staff accounts (admin only)
- `POST /api/users` — create a new staff account with bcrypt-hashed password (admin only)
- `PUT /api/users/{email}` — update name, role, password, or assigned subjects (admin only)
- `POST /api/predict` — RandomForest pass-probability prediction; accepts subject, assess1_mark, assess2_mark (optional); returns pass probability %, prediction label, risk level, risk colour, confidence record count, and Gemini one-sentence advice; admins also receive model name and accuracy
- `POST /api/gemini/alert` — one-sentence performance alert for a subject/trimester scope
- `POST /api/gemini/analyse` — 4–5 sentence deep-dive analysis for a subject/trimester scope
- `POST /api/gemini/ask` — free Q&A answering a question about a subject's data in 2–3 sentences
- `GET /api/health` and `GET /health` — health check endpoints

#### Backend — ML
- **`backend/app/ml/train_model.py`** — standalone training script; reads `_DATA` (or a CSV path); engineers features: Assessment 1 mark, Assessment 2 mark, subject difficulty index, trimester number; trains a `RandomForestClassifier`; serialises model to `best_model.pkl`, metadata to `model_meta.pkl`, subject difficulty map to `subject_difficulty.pkl`
- **`backend/app/ml/best_model.pkl`** — trained RandomForest binary classifier (Pass / Fail)
- **`backend/app/ml/model_meta.pkl`** — stores model name and accuracy score shown on the Predictive Reports page

### Changed
- **`Sidebar.jsx`** — full role-based rewrite; `LECTURER_NAV` and `ADMIN_NAV_BASE` / `ADMIN_NAV_SUPER` arrays define nav per role; `isSuperAdmin` check gates Audit Log and User Management; user avatar, name, and role displayed at the bottom; collapse/expand state retained; all SVG icons defined inline
- **`App.js`** — role-based route guards (`PrivateRoute`, `AdminRoute`, `Protected`, `AdminProtected`); separate routes for `/dashboard/admin` and `/dashboard/lecturer`; all new page routes added; `SettingsPage` wrapper renders role-appropriate settings component
- **`AuditLog.jsx`** — updated to call `GET /api/audit-logs` with filter params; table with action type, status, user, and timestamp columns; export button

### Fixed
- Lecturer users were redirected to admin dashboard on login; fixed by reading `user.role` from the JWT response and routing to the correct path
- Sidebar nav links had no matching `<Route>` for `/explorer` and `/settings`; routes added in `App.js`

---

## [Unreleased] — 2026-04-26

### Added

#### Frontend — Pages
- **`AdminDashboard.jsx`** (`/dashboard/admin`) — institution-wide analytics for the Head of Technology; KPI cards (total students, overall pass rate, average mark, at-risk count); six Recharts panels (grade distribution bar chart, pass/fail donut, performance trend line, assessment comparison bar, international/domestic split, difficulty index); year/trimester filter controls; institution-level GeminiPanel for AI insights
- **`AdminExplorer.jsx`** (`/student-analytics`) — admin student record browser; subject + trimester + search filters with paginated table; click-through to individual student detail panel showing mark timeline chart, assessment breakdown table with inline mark bars, and pass/fail badge
- **`LecturerDashboard.jsx`** (`/dashboard/lecturer`) — per-lecturer dashboard filtered to the lecturer's assigned subjects; KPI cards (enrolled students, pass rate, avg mark, at-risk count) with period-over-period delta badges; grade distribution, pass/fail donut, performance trend, assessment comparison, and international split charts; GeminiPanel at the bottom for subject-level AI alerts, full analysis, and Q&A
- **`LecturerExplorer.jsx`** (`/explorer`) — student record explorer scoped to the lecturer's subjects; subject, trimester, search, and pass/fail filters; paginated results table with inline mark progress bar and pass badge; sidebar student detail with mark timeline and GeminiPanel "Predict" shortcut
- **`LecturerPredictor.jsx`** (`/predictor`) — ML prediction tool; subject selector pre-populated from the lecturer's assigned subjects; Assessment 1 and Assessment 2 mark inputs; calls `POST /api/predict` and displays predicted final mark, letter grade, and risk category with colour-coded result card
- **`LecturerSettings.jsx`** (`/settings`) — profile page showing name, email, role, and assigned subjects; change-password section (current + new + confirm, calls `POST /api/auth/change-password`); notification preferences panel (subject-level toggles persisted to `localStorage`)
- **`SubjectAnalytics.jsx`** (`/analytics/subjects`) — admin subject-level analytics; searchable subject dropdown, trimester filter; grade distribution bar chart, performance trend line chart, assessment comparison; subject summary table with pass rate and average mark columns
- **`UserManagement.jsx`** (`/users`) — admin CRUD for lecturer accounts; table of all users with role badge and active status; inline edit form to update name/role/subjects; create-lecturer form with auto-generated secure password; calls `GET /POST /PUT /api/users`
- **`Login.jsx`** — rewritten login page in JSX with password visibility toggle and role-based redirect (`/dashboard/admin` for Head of Technology, `/dashboard/lecturer` for Lecturer)

#### Frontend — Components
- **`GeminiPanel.jsx`** — reusable three-level AI insights panel; Level 1 auto-fetches a performance alert when subject/trimester change; Level 2 shows a full deep-dive analysis on demand; Level 3 provides a Q&A interface with a 3-message rolling history; used in LecturerDashboard, LecturerExplorer, and AdminDashboard

#### Frontend — Utilities
- **`frontend/src/utils/auth.js`** — shared auth helpers: `getUser()`, `getToken()`, `isAdmin()`, `isLecturer()`, `logout()`; all read from `localStorage` keys `edapt_user` / `edapt_token`

#### Backend — API Endpoints (`backend/app/main.py`)
- `GET /api/dashboard/summary` — overall KPI metrics (total students, pass rate, average mark, at-risk count) with optional `subject` and `period` filters
- `GET /api/dashboard/grade-distribution` — grade band counts (0–49, 50–59, … 90–100) per subject/period
- `GET /api/dashboard/performance-trend` — average mark by trimester across configured periods
- `GET /api/dashboard/assessment-comparison` — mean Assessment 1 vs Assessment 2 vs Final by subject
- `GET /api/dashboard/pass-fail` — pass and fail counts for a subject/period
- `GET /api/dashboard/international` — international vs domestic student counts and pass rates
- `GET /api/dashboard/difficulty-index` — subjects ranked by fail rate (difficulty proxy)
- `GET /api/dashboard/classgroups` — breakdown by class group with average marks
- `GET /api/explorer/records` — paginated student records with filters (subject, period, search term, pass/fail)
- `GET /api/explorer/filters` — available subject and period values for filter dropdowns
- `GET /api/explorer/student/{student_id}` — full record for a single student including all subject marks
- `GET /api/explorer/export` — export current filtered view as a downloadable CSV
- `GET /api/subjects/list` — flat list of distinct subject codes
- `GET /api/subjects/analytics` — per-subject summary stats for the Subject Analytics page
- `GET /api/users` — list all staff accounts (admin only)
- `POST /api/users` — create a new staff account with hashed password (admin only)
- `PUT /api/users/{email}` — update name, role, subjects, or active status for a user (admin only)
- `POST /api/predict` — RandomForest final-mark prediction; accepts `subject`, `assess1`, `assess2`; returns `predicted_mark`, `grade`, `risk_category`
- `POST /api/gemini/alert` — generate a short AI performance alert for a given subject + trimester
- `POST /api/gemini/analyse` — generate a full AI deep-dive analysis for a subject + trimester
- `POST /api/gemini/ask` — answer a free-text question about a subject's data
- `POST /api/gemini/institution-alert` — institution-wide AI performance alert (admin)
- `POST /api/gemini/institution-analyse` — institution-wide AI analysis (admin)
- `POST /api/gemini/institution-ask` — institution-wide Q&A (admin)
- `GET /api/gemini/token-log` — view per-request Gemini API token usage log
- `POST /api/auth/change-password` — update password for the authenticated user (requires current password)
- `POST /api/auth/logout` — logout endpoint (client-side token removal; returns 200)

#### Backend — ML
- **`backend/app/ml/train_model.py`** — standalone script to train the RandomForest final-mark predictor; reads the ingested dataset, engineers features (subject encoding, assess1, assess2), trains with `sklearn`, and serialises the model to `backend/app/ml/model.pkl`

### Changed
- **`frontend/src/App.js`** — role-based route guards (`AdminRoute` / `AdminProtected`); separate dashboard routes for admin (`/dashboard/admin`) and lecturer (`/dashboard/lecturer`); added all new page routes; `/users` now mounts `UserManagement`; `/analytics/subjects` added as an admin-only route
- **`frontend/src/components/Sidebar.jsx`** — role-aware navigation: lecturers see Dashboard / Explorer / Predictor / Settings; admins see Dashboard / Subject Analytics / Student Analytics / Predictive Reports / Data Ingestion / Audit Log / User Management / Settings; active link highlighted; collapse/expand behaviour retained

---

## [Unreleased] — 2026-04-24

### Added
- **Collapsible sidebar** (`frontend/src/components/Sidebar.jsx`) — toggle button collapses sidebar from 220 px (icons + labels) to 64 px (icons only); width animates with CSS transition; tooltips appear on icon hover when collapsed
- **Shared layout component** (`frontend/src/components/Layout.jsx`) — wraps the collapsible sidebar and a scrollable main content area; used by all protected pages so sidebar is consistent across the entire app
- **Welcome banner on Dashboard** — reads `edapt_user` from `localStorage` and displays "Welcome back, [name]. Thank you for your work today." as a gradient card above the analytics charts
- **User info panel at sidebar bottom** — shows the logged-in user's initials avatar, full name, and role (read from `localStorage`); collapses to avatar-only when sidebar is collapsed
- **Explorer page** (`frontend/src/pages/Explorer.jsx`) — placeholder page for the upcoming student record browser; wired to `/explorer` route
- **Settings page** (`frontend/src/pages/Settings.jsx`) — displays account info (name, email, role) from `localStorage`; placeholder section for future preferences; wired to `/settings` route
- **`POST /api/ingest` router** (`backend/app/api/routes/ingest.py`) — extracted from `main.py` into its own router; accepts `.csv`, `.xlsx`, `.json` uploads, parses with pandas, returns `row_count`, `columns`, and a 10-row preview; writes a `Data Upload` audit event on success
- **`GET /api/audit-logs` router** (`backend/app/api/routes/audit.py`) — extracted from `main.py` into its own router; supports optional query filters: `uid`, `action_type`, `status`, `role`

### Changed
- **`frontend/src/App.js`** — all six protected routes now render inside `<Layout>` (unified sidebar layout); removed the old top header (`app-header`) and the `SIDEBAR_ROUTES` split logic; added routes for `/explorer` and `/settings`; root `/` redirects to `/dashboard`
- **`frontend/src/pages/DataIngestion.jsx`** — removed the embedded `<Sidebar />` import and outer `flex` wrapper (Layout now provides both); page now returns its content directly, matching the shared Layout padding and background
- **`frontend/src/pages/AuditLog.jsx`** — same as DataIngestion: removed embedded `<Sidebar />` and outer wrapper
- **`backend/app/main.py`** — cleaned up to only contain app setup, middleware, and router registration; all business logic moved to dedicated route files; imports reduced from 10 to 6
- **`frontend/src/components/Sidebar.jsx`** — rewritten to support collapsible state; nav item for Dashboard updated from `/` to `/dashboard`; logout button clears both `edapt_token` and `edapt_user` from `localStorage` before redirecting

### Fixed
- All six sidebar navigation links now navigate to their correct routes — previously Explorer (`/explorer`) and Settings (`/settings`) had no matching `<Route>` and would silently 404
- Pages that previously embedded their own `<Sidebar />` (DataIngestion, AuditLog) no longer render a second sidebar when placed inside Layout

---

## [Unreleased] — 2026-04-17

### Added
- `POST /api/v1/auth/register` — create staff/admin accounts (bcrypt-hashed password, no PII)
- `POST /api/v1/auth/login` — OAuth2 password flow returning a JWT access token
- `GET /api/v1/auth/me` — return current authenticated user profile
- `User` ORM model (`backend/app/db/models.py`) — `id`, `name`, `email`, `hashed_password`, `role`, `is_active`, audit timestamps
- `frontend/src/Login.js` + `Login.css` — sign-in page with email/password form, error banner, loading spinner, and "Account created" success notice on arrival from signup
- `frontend/src/Signup.js` + `Signup.css` — registration page wired to `POST /api/v1/auth/register` with loading/error states, confirm-password validation, and redirect to login on success
- Password show/hide eye-icon toggle on all password fields (Login and Signup), inline SVG, no extra dependencies
- `PrivateRoute` in `App.js` — redirects unauthenticated users to `/login`

### Fixed
- `backend/app/main.py` — auth router was registered before `app = FastAPI(...)` was created, causing a `NameError` and silently dropping all auth routes; moved `include_router` call to after app initialisation
- `backend/app/db/models.py` — `AuditMixin` used bare `datetime` type annotations which SQLAlchemy 2.0 rejects on plain-Python mixins; removed annotations (Column definitions are sufficient)
- `backend/app/db/models.py` — stray paste comment removed from above the `User` class
- `frontend/src/Login.js` — "Account created!" banner persisted across page refreshes because `location.state` survives browser history; cleared with `window.history.replaceState` on mount

### Dependencies added (`backend/requirements.txt`)
- `pydantic[email]==2.9.2` — required for `EmailStr` on the register schema
- `python-multipart==0.0.9` — required for OAuth2 form-encoded login body
- `bcrypt==3.2.2` — pinned to `<4.x`; `passlib 1.7.4` is incompatible with `bcrypt 4.x` (72-byte password limit triggers an error during passlib's internal bug-detection test)

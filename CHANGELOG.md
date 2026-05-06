# Changelog

All notable changes to EDAPT v2 are documented here.

---

## [Unreleased] — 2026-04-26

### Added

#### Frontend — Pages
- **`AdminDashboard.jsx`** (`/dashboard/admin`) — institution-wide analytics for the Head of Technology; KPI cards (total students, overall pass rate, average mark, at-risk count); six Recharts panels (grade distribution bar chart, pass/fail donut, performance trend line, assessment comparison bar, international/domestic split, difficulty index); year/trimester filter controls; institution-level GeminiPanel for AI insights
- **`AdminExplorer.jsx`** (`/student-analytics`) — admin student record browser; subject + trimester + search filters with paginated table; click-through to individual student detail panel showing mark timeline chart, assessment breakdown table with inline mark bars, and pass/fail badge
- **`LecturerDashboard.jsx`** (`/dashboard/lecturer`) — per-lecturer dashboard filtered to the lecturer's assigned subjects; KPI cards (enrolled students, pass rate, avg mark, at-risk count) with period-over-period delta badges; grade distribution, pass/fail donut, performance trend, assessment comparison, and international split charts; GeminiPanel at the bottom for subject-level AI alerts, full analysis, and Q&A
- **`LecturerExplorer.jsx`** (`/explorer`) — student record explorer scoped to the lecturer's subjects; subject, trimester, search, and pass/fail filters; paginated results table with inline mark progress bar and pass badge; sidebar student detail with mark timeline and GeminiPanel "Predict" shortcut
- **`LecturerPredictor.jsx`** (`/predictor`) — ML prediction tool; subject selector pre-populated from the lecturer's assigned subjects; Assessment 1 and Assessment 2 mark inputs (pre-fillable via URL query params `?subject=&mark=`); calls `POST /api/predict` and displays predicted final mark, letter grade, and risk category with colour-coded result card
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

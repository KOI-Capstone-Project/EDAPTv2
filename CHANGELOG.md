# Changelog

All notable changes to EDAPT v2 are documented here.

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

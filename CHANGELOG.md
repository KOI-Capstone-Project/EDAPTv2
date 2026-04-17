# Changelog

All notable changes to EDAPT v2 are documented here.

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

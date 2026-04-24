# EDAPT v2 — Educational Data Analytics and Predictive Tool

> King's Own Institute (KOI) Capstone Project

---

## Tech stack

| Layer       | Technology                                        |
|-------------|---------------------------------------------------|
| Backend     | Python 3.12 · FastAPI · SQLAlchemy (async)        |
| Database    | PostgreSQL 16                                     |
| ML          | Scikit-Learn · Pandas                             |
| Frontend    | React 18 · React Router v6 · Recharts · Axios     |
| AI insights | Google Gemini API                                 |
| Container   | Docker · Docker Compose                           |
| Proxy       | nginx (production)                                |

---

## Pages

| Route            | Description                                      |
|------------------|--------------------------------------------------|
| `/login`         | JWT login (email + password)                     |
| `/signup`        | New account registration                         |
| `/dashboard`     | Mode 1 — Descriptive Analytics + welcome banner  |
| `/predictions`   | Mode 2 — Predictive Analytics (ML inference)     |
| `/data-ingestion`| Upload CSV / XLSX / JSON datasets                |
| `/audit-log`     | System event history with filters                |
| `/explorer`      | Student record browser (coming soon)             |
| `/settings`      | Account info and preferences                     |

All routes except `/login` and `/signup` are protected — unauthenticated users are automatically redirected to `/login`.

---

## Project structure

```
EDAPTv2/
├── backend/
│   ├── app/
│   │   ├── api/routes/
│   │   │   ├── auth.py          # POST /register · POST /login · GET /me
│   │   │   ├── ingest.py        # POST /api/ingest
│   │   │   ├── audit.py         # GET /api/audit-logs
│   │   │   ├── assessments.py   # GET /api/v1/assessments
│   │   │   ├── predictions.py   # POST /api/v1/predictions/run
│   │   │   ├── students.py
│   │   │   └── subjects.py
│   │   ├── core/
│   │   │   ├── config.py        # Pydantic settings (.env)
│   │   │   ├── security.py      # JWT + bcrypt helpers
│   │   │   └── audit.py         # In-memory audit log + append_event()
│   │   ├── db/
│   │   │   ├── models.py        # SQLAlchemy ORM models
│   │   │   ├── session.py       # Async engine + get_db dependency
│   │   │   └── base.py
│   │   ├── ml/predictor.py      # Scikit-Learn pipeline
│   │   └── main.py              # FastAPI app entry point
│   ├── tests/
│   ├── requirements.txt
│   ├── Dockerfile.dev
│   └── Dockerfile.prod
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Sidebar.jsx      # Collapsible sidebar navigation
│   │   │   └── Layout.jsx       # Sidebar + main content wrapper
│   │   ├── pages/
│   │   │   ├── Dashboard.js     # Mode 1 — Descriptive Analytics
│   │   │   ├── Predictions.js   # Mode 2 — Predictive Analytics
│   │   │   ├── DataIngestion.jsx
│   │   │   ├── AuditLog.jsx
│   │   │   ├── Explorer.jsx
│   │   │   └── Settings.jsx
│   │   ├── services/api.js      # Axios client (JWT interceptor)
│   │   ├── Login.js
│   │   ├── Signup.js
│   │   └── App.js               # Routes + PrivateRoute guard
│   ├── public/
│   ├── Dockerfile.dev
│   └── Dockerfile.prod
├── nginx/nginx.conf             # Production reverse proxy
├── scripts/sql/                 # DB seed files
├── docker-compose.yml           # Development
├── docker-compose.prod.yml      # Production
├── .env.example
└── .gitignore
```

---

## Quick start (development)

### Prerequisites
- Docker Desktop ≥ 4.x
- Git

### 1 — Clone and configure

```bash
git clone https://github.com/KOI-Capstone-Project/EDAPTv2.git
cd EDAPTv2
cp .env.example .env
# Edit .env — set GEMINI_API_KEY and change default passwords
```

### 2 — Start all services

```bash
docker compose up --build
```

| Service    | URL                        | Notes                      |
|------------|----------------------------|----------------------------|
| Frontend   | http://localhost:3000      | React dev server           |
| Backend    | http://localhost:8000      | FastAPI + auto-reload      |
| API Docs   | http://localhost:8000/docs | Swagger UI                 |
| pgAdmin    | http://localhost:5050      | DB GUI                     |

### 3 — Stop

```bash
docker compose down        # keep volumes (DB data preserved)
docker compose down -v     # also wipe the DB volume (fresh start)
```

---

## Running without Docker

Open two separate terminals:

**Terminal 1 — Backend**
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — Frontend**
```bash
cd frontend
npm install
npm start
```

> You will need PostgreSQL running locally and the `DATABASE_URL` in `.env` pointing to it.

---

## Production deployment

```bash
cp .env.example .env
# Set ENVIRONMENT=production, strong passwords, GEMINI_API_KEY

docker compose -f docker-compose.prod.yml up --build -d
```

The nginx proxy listens on port 80. Add TLS certs to `nginx/certs/` and extend `nginx/nginx.conf` with an HTTPS server block.

---

## Environment variables

Copy `.env.example` to `.env` and fill in:

| Variable                   | Description                               |
|----------------------------|-------------------------------------------|
| `POSTGRES_USER`            | DB username                               |
| `POSTGRES_PASSWORD`        | DB password                               |
| `POSTGRES_DB`              | Database name                             |
| `DATABASE_URL`             | Full asyncpg DSN (auto-built from above)  |
| `SECRET_KEY`               | JWT signing secret (change in production) |
| `GEMINI_API_KEY`           | Google Gemini API key                     |
| `PGADMIN_DEFAULT_EMAIL`    | pgAdmin login email                       |
| `PGADMIN_DEFAULT_PASSWORD` | pgAdmin login password                    |
| `REACT_APP_API_BASE_URL`   | API base URL seen by the browser          |

---

## Authentication

- Login stores a JWT in `localStorage` as `edapt_token` and user profile as `edapt_user`
- All API requests attach the token via an Axios interceptor (`Authorization: Bearer <token>`)
- Tokens expire after **8 hours** (one work day)
- The sidebar reads `edapt_user` to display the logged-in user's name, initials, and role

---

## Sidebar navigation

The sidebar is collapsible:
- **Expanded** (220 px) — shows icons + labels
- **Collapsed** (64 px) — shows icons only; hover tooltips show labels

Clicking the chevron button at the top toggles between modes. The logout button clears `localStorage` and redirects to `/login`.

---

## Data pipeline

```
CSV / XLSX / JSON file
        ↓
  POST /api/ingest          ← authenticated upload
        ↓
  pandas parse + validate
        ↓
  Anonymise (PII stripped)
        ↓
  PostgreSQL (assessments, enrollments, students)
        ↓
  POST /api/v1/predictions/run
        ↓
  RandomForest inference → pass_probability
        ↓
  Google Gemini API → gemini_insight (contextual text)
        ↓
  predictions table → Dashboard / Predictor page
```

Every ingest and login event is written to the audit log (`GET /api/audit-logs`).

---

## Database schema

Ten tables across three layers:

**Dimension / lookup:** `countries`, `programs`, `trimesters`, `subjects`, `class_groups`, `lecturers`

**Core entity:** `students` — stores only `student_masked_id` (integer). No PII.

**Fact / output:** `enrollments`, `assessments`, `predictions`

**Auth:** `users` — name, email (unique), bcrypt-hashed password, role (`admin` / `staff`)

See [backend/app/db/models.py](backend/app/db/models.py) for full column definitions.

---

## ML pipeline (Mode 2)

- Trained on data up to **T2 2025**
- Target: **Pass / Fail** classification for T3 2025
- Algorithm: `RandomForestClassifier` (200 trees, `max_depth=8`)
- Target accuracy: **> 75%**
- Model serialised to `backend/app/ml/saved_models/rf_v1.joblib`
- Predictions stored with `pass_probability` and `gemini_insight` fields

Trigger inference via:
```
POST /api/v1/predictions/run?trimester_id=<id>&model_version=rf_v1
```

---

## Running tests

```bash
docker compose exec backend pytest tests/ -v
```

---

## Contributing

1. Branch from `main`: `git checkout -b feature/your-feature`
2. Commit with conventional messages: `feat:`, `fix:`, `chore:`
3. Open a pull request against `main`

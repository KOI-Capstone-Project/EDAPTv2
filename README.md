# EDAPT v2 — Educational Data Analytics and Predictive Tool

> King's Own Institute (KOI) Capstone Project

---

## Tech stack

| Layer       | Technology                          |
|-------------|-------------------------------------|
| Backend     | Python 3.12 · FastAPI · SQLAlchemy  |
| Database    | PostgreSQL 16                       |
| ML          | Scikit-Learn · Pandas               |
| Frontend    | React 18 · Recharts                 |
| AI insights | Google Gemini API                   |
| Container   | Docker · Docker Compose             |
| Proxy       | nginx (production)                  |

---

## Project structure

```
EDAPTv2/
├── backend/
│   ├── app/
│   │   ├── api/routes/        # FastAPI routers
│   │   ├── core/config.py     # Pydantic settings
│   │   ├── db/
│   │   │   ├── models.py      # SQLAlchemy ORM models
│   │   │   ├── session.py     # Async engine + get_db dependency
│   │   │   └── base.py        # Alembic-friendly base import
│   │   ├── ml/predictor.py    # Scikit-Learn pipeline
│   │   └── main.py            # FastAPI app + lifespan
│   ├── tests/
│   ├── requirements.txt
│   ├── Dockerfile.dev
│   └── Dockerfile.prod
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.js   # Mode 1 — Descriptive
│   │   │   └── Predictions.js # Mode 2 — Predictive
│   │   ├── services/api.js    # Axios client
│   │   └── App.js
│   ├── public/
│   ├── Dockerfile.dev
│   └── Dockerfile.prod
├── nginx/nginx.conf           # Production reverse proxy
├── scripts/sql/               # DB seed files
├── docker-compose.yml         # Development
├── docker-compose.prod.yml    # Production
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
# Edit .env — set GEMINI_API_KEY and change passwords
```

### 2 — Start all services

```bash
docker compose up --build
```

| Service   | URL                          |
|-----------|------------------------------|
| Frontend  | http://localhost:3000        |
| API       | http://localhost:8000        |
| API docs  | http://localhost:8000/docs   |
| pgAdmin   | http://localhost:5050        |

### 3 — Stopping

```bash
docker compose down          # keep volumes
docker compose down -v       # also wipe DB volume
```

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

| Variable                  | Description                               |
|---------------------------|-------------------------------------------|
| `POSTGRES_USER`           | DB username                               |
| `POSTGRES_PASSWORD`       | DB password                               |
| `POSTGRES_DB`             | Database name                             |
| `DATABASE_URL`            | Full asyncpg DSN (auto-built from above)  |
| `SECRET_KEY`              | FastAPI secret (JWT / sessions)           |
| `GEMINI_API_KEY`          | Google Gemini API key                     |
| `PGADMIN_DEFAULT_EMAIL`   | pgAdmin login email                       |
| `PGADMIN_DEFAULT_PASSWORD`| pgAdmin login password                    |
| `REACT_APP_API_BASE_URL`  | API base URL seen by the browser          |

---

## Database schema

Ten tables across three layers:

**Dimension / lookup:** `countries`, `programs`, `trimesters`, `subjects`, `class_groups`, `lecturers`

**Core entity:** `students` — stores only `student_masked_id` (integer). No PII.

**Fact / output:** `enrollments`, `assessments`, `predictions`

See `backend/app/db/models.py` for full column definitions and constraints.

---

## ML pipeline (Mode 2)

- Trained on data up to **T2 2025**
- Target: **Pass / Fail** classification for T3 2025
- Algorithm: `RandomForestClassifier` (200 trees, `max_depth=8`)
- Target accuracy: **> 75 %**
- Model serialised to `backend/app/ml/saved_models/rf_v1.joblib`
- Predictions stored in the `predictions` table with `pass_probability` and `gemini_insight`

Trigger training / inference via:
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

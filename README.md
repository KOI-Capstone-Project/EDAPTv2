# EDAPT v2 — Educational Data Analytics and Predictive Tool

> King's Own Institute (KOI) — Capstone Project (Second Year)

EDAPT v2 is a role-based academic analytics platform. It lets **Lecturers** explore their class performance and get AI-generated insights, while the **Head of Technology** has full institution-wide analytics, data ingestion, user management, and predictive reports.

---

## Tech Stack

| Layer       | Technology                                       |
|-------------|--------------------------------------------------|
| Backend     | Python 3.12 · FastAPI · Uvicorn                  |
| Data / ML   | Pandas · Scikit-Learn · Joblib · NumPy           |
| AI          | Google Gemini API (Flash + Pro models)           |
| Auth        | JWT (python-jose) · Bcrypt (passlib)             |
| Frontend    | React 18 · React Router v6 · Recharts · Axios   |
| Styling     | Inline styles (no CSS framework)                 |

> **No database required.** All student data is loaded from a CSV/XLSX file into an in-memory pandas DataFrame at runtime. User accounts are stored in memory and reset on server restart.

---

## Roles

| Role                   | Access                                                              |
|------------------------|---------------------------------------------------------------------|
| `Lecturer`             | Their own subject dashboard, explorer, predictor, AI insights       |
| `Head of Technology`   | Full institution analytics, data ingestion, all subjects            |
| Super-admin (`admin`)  | All of the above + audit log and user management                    |

The super-admin account has the fixed email `admin`. All other Head of Technology accounts can see analytics but not audit logs or user management.

---

## Pages & Routes

### Lecturer (role: Lecturer)

| Route                | Page               | Description                                      |
|----------------------|--------------------|--------------------------------------------------|
| `/dashboard/lecturer`| Lecturer Dashboard | KPI cards, grade charts, pass/fail donut, trends |
| `/explorer`          | Explorer           | Coming in next release                           |
| `/predictor`         | Predictor          | Coming in next release                           |
| `/ai-insights`       | AI Insights        | Gemini-powered analysis scoped to your subjects  |
| `/settings`          | Settings           | Change name, email, password                     |

### Admin (role: Head of Technology)

| Route                 | Page                | Description                                            |
|-----------------------|---------------------|--------------------------------------------------------|
| `/dashboard/admin`    | Admin Dashboard     | Institution-wide KPIs, charts, filters, Gemini alerts  |
| `/subject-analytics`  | Subject Analytics   | Compare two subjects side-by-side across trimesters    |
| `/student-analytics`  | Student Analytics   | Paginated student record explorer + drill-down detail  |
| `/predictive-reports` | Predictive Reports  | ML pass-probability predictor + Gemini advice          |
| `/data-ingestion`     | Data Ingestion      | Upload CSV/XLSX, preview data, paginate                |
| `/audit-log`          | Audit Log           | Event history (super-admin only)                       |
| `/users`              | User Management     | Create, edit, delete accounts (super-admin only)       |
| `/settings`           | Settings            | Change name, email, password                           |

---

## Project Structure

```
EDAPTv2/
├── backend/
│   └── app/
│       ├── main.py              # FastAPI app — all routes, auth, ML, Gemini
│       └── ml/
│           ├── train_model.py   # Train & save the ML model
│           ├── best_model.pkl   # Trained RandomForest classifier
│           ├── model_meta.pkl   # Accuracy + model name metadata
│           ├── subject_difficulty.pkl  # Per-subject difficulty index
│           └── predictor.py     # Inference helpers
├── frontend/
│   └── src/
│       ├── App.js               # Routes + Protected/AdminProtected guards
│       ├── components/
│       │   ├── Layout.jsx       # Sidebar + main content wrapper
│       │   ├── Sidebar.jsx      # Collapsible role-aware sidebar
│       │   ├── GeminiPanel.jsx  # 3-level AI panel (alert, analyse, Q&A)
│       │   ├── PageUnavailable.jsx  # Shared "coming soon" page
│       │   └── ErrorBoundary.jsx
│       ├── pages/
│       │   ├── Login.jsx
│       │   ├── LecturerDashboard.jsx
│       │   ├── LecturerAIInsights.jsx
│       │   ├── LecturerExplorer.jsx
│       │   ├── LecturerPredictor.jsx
│       │   ├── LecturerSettings.jsx
│       │   ├── AdminDashboard.jsx
│       │   ├── SubjectAnalytics.jsx
│       │   ├── AdminExplorer.jsx      # Student Analytics
│       │   ├── AdminPredictor.jsx     # Predictive Reports
│       │   ├── DataIngestion.jsx
│       │   ├── AuditLog.jsx
│       │   ├── UserManagement.jsx
│       │   └── AdminSettings.jsx
│       ├── services/api.js      # Axios instance with JWT interceptor
│       └── utils/auth.js        # getUser, getToken, getUserName helpers
├── data/                        # Place your CSV/XLSX dataset here
├── docker-compose.yml
├── docker-compose.prod.yml
└── nginx/
```

---

## Quick Start (without Docker)

Open **two terminals** from the project root.

### Prerequisites

- Python 3.12+
- Node.js 18+ and npm
- A `GEMINI_API_KEY` from [Google AI Studio](https://aistudio.google.com/)

---

### Terminal 1 — Backend

```bash
cd backend

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set your Gemini API key
export GEMINI_API_KEY="your-key-here"   # Windows: set GEMINI_API_KEY=your-key-here

# Start the server
uvicorn app.main:app --reload --port 8000
```

API available at: `http://localhost:8000`
Swagger docs at: `http://localhost:8000/docs`

---

### Terminal 2 — Frontend

```bash
cd frontend
npm install
npm start
```

App available at: `http://localhost:3000`

---

## Default Login

| Email   | Password  | Role                 |
|---------|-----------|----------------------|
| `admin` | `admin123`| Head of Technology (super-admin) |

Use **User Management** (super-admin only) to create additional accounts for lecturers or other admin users.

---

## Loading Data

1. Log in as the `admin` account
2. Navigate to **Data Ingestion** in the sidebar
3. Upload a `.csv` or `.xlsx` file with the expected columns (see below)
4. Click **Process & Preview** — the data loads into memory immediately
5. All analytics pages update to reflect the uploaded dataset

### Expected Columns

| Column               | Description                        |
|----------------------|------------------------------------|
| `STUDENTID_MASKED`   | Anonymised student identifier      |
| `SUBJECTCODE`        | Subject code (e.g. `ICT101`)       |
| `ASSESSMENTTYPECODE` | Assessment type (e.g. `Quiz`, `Exam`) |
| `MARKPERCENT`        | Mark as a percentage (0–100)       |
| `STUDYPERIOD`        | Trimester code (e.g. `24.2`)       |
| `COUNTRY_MASKED`     | Student's origin country (masked)  |
| `GENDERCODE`         | Gender code                        |
| `AGEGROUP`           | Age group bracket                  |
| `CLASSGROUP`         | Class group label                  |

Columns not in the list are ignored. Missing optional columns degrade gracefully (charts simply show no data for that dimension).

---

## Training the ML Model

The ML model predicts pass probability from Assessment 1 mark, Assessment 2 mark (optional), subject difficulty, and trimester.

```bash
cd backend
source venv/bin/activate
python app/ml/train_model.py
```

This reads from the in-memory data (you must have data loaded via ingestion first, or point the script at a CSV) and writes three `.pkl` files to `backend/app/ml/`. The backend loads these automatically on startup.

The model is a `RandomForestClassifier`. Accuracy and model name are shown on the **Predictive Reports** page header.

---

## AI Insights (Gemini)

Three tiers of AI are available throughout the app, all powered by the Google Gemini API:

| Tier | Endpoint | Trigger | Scope |
|------|----------|---------|-------|
| 1 — Auto Alert | `POST /api/gemini/alert` | On page load | Subject + trimester |
| 2 — Deep Analysis | `POST /api/gemini/analyse` | Click button | Subject + trimester |
| 3 — Free Q&A | `POST /api/gemini/ask` | User question | Subject + trimester |

Admin-level equivalents (`/api/gemini/institution-*`) are used on the Admin Dashboard and Predictive Reports for institution-wide context.

Set `GEMINI_API_KEY` before starting the backend. Without it, AI features will fail silently (no crash, just empty responses).

---

## Authentication

- JWT tokens are stored in `localStorage` as `edapt_token`
- User profile is stored as `edapt_user` (JSON)
- Tokens expire after **8 hours**
- All API requests attach the token via an Axios request interceptor
- Role checking happens both on the frontend (route guards) and the backend (`require_admin` / `require_super_admin` dependencies)

---

## API Overview

| Group     | Key Endpoints                                                                                      |
|-----------|----------------------------------------------------------------------------------------------------|
| Auth      | `POST /api/auth/login` · `POST /api/auth/logout` · `POST /api/auth/change-password`               |
| Dashboard | `GET /api/dashboard/summary` · `grade-distribution` · `performance-trend` · `assessment-comparison` · `pass-fail` · `international` · `difficulty-index` |
| Explorer  | `GET /api/explorer/records` · `GET /api/explorer/filters` · `GET /api/explorer/student/{id}` · `GET /api/explorer/export` |
| Subjects  | `GET /api/subjects/list` · `GET /api/subjects/analytics`                                           |
| Ingest    | `POST /api/ingest` · `GET /api/ingest/preview`                                                     |
| ML        | `POST /api/predict`                                                                                |
| Gemini    | `POST /api/gemini/alert` · `analyse` · `ask` · `institution-alert` · `institution-analyse` · `institution-ask` · `GET /api/gemini/token-log` |
| Users     | `GET /api/users` · `POST /api/users` · `PUT /api/users/{email}` · `DELETE /api/users/{email}`     |
| Audit     | `GET /api/audit-logs`                                                                              |

Full interactive docs: `http://localhost:8000/docs`

---

## Sidebar Navigation

The sidebar is collapsible (toggle with the chevron button at the top):

- **Expanded** (220 px) — icons + labels
- **Collapsed** (64 px) — icons only with hover tooltips

Nav items shown depend on role:

- **Lecturer**: Dashboard · Explorer · Predictor · AI Insights · Settings
- **Admin**: Dashboard · Subject Analytics · Student Analytics · Predictive Reports · Data Ingestion · Settings
- **Super-admin** (admin email only): All of the above + Audit Log · User Management

---

## Branch Strategy

| Branch        | Purpose                        |
|---------------|--------------------------------|
| `main`        | Stable, reviewed code          |
| `sangam_dev`  | Active development             |

PRs are opened from `sangam_dev` → `main`.

---

## Authors

- **Sangam Ghale Gurung** — Full-stack development, ML pipeline, AI integration

King's Own Institute · Bachelor of Information Technology · Capstone Project 1 · 2025

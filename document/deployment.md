# EDAPT v2 — Deployment Guide

## Overview

EDAPT v2 uses a three-service hosting stack that is entirely free and requires no credit card.

| Layer | Platform | URL pattern |
|---|---|---|
| Frontend (React) | Vercel | `https://edaptv2-git-<branch>.vercel.app` |
| Backend (FastAPI) | Hugging Face Spaces | `https://<hf-username>-edaptv2-backend.hf.space` |
| Database (PostgreSQL) | Neon.tech | Internal — connection string only |

Branch preview URLs are created automatically by Vercel on every push. Each branch gets its own frontend URL pointing to the shared backend.

---

## Prerequisites

| Account | URL | Cost |
|---|---|---|
| GitHub | github.com | Free |
| Vercel | vercel.com | Free (Hobby) |
| Hugging Face | huggingface.co | Free |
| Neon | neon.tech | Free |
| Google AI Studio | aistudio.google.com | Free (Gemini API key) |

---

## Step 1 — Database (Neon.tech)

1. Sign up at [neon.tech](https://neon.tech) with GitHub.
2. Create a new project — name it `edaptv2`.
3. Go to **Connection Details** and copy the **asyncpg** connection string:
   ```
   postgresql+asyncpg://<user>:<password>@<host>.neon.tech/<dbname>
   ```
4. Keep this string — it is needed in Steps 2 and 3.

> Neon automatically provisions the schema on first backend startup via SQLAlchemy's `create_all`.

---

## Step 2 — Backend (Hugging Face Spaces)

### 2a. Create the Space

1. Go to [huggingface.co/new-space](https://huggingface.co/new-space).
2. Fill in:
   - **Space name:** `edaptv2-backend`
   - **SDK:** Docker
   - **Visibility:** Public
3. Click **Create Space**.

### 2b. Set environment variables

In the Space → **Settings** → **Variables and secrets**, add:

| Key | Value | Type |
|---|---|---|
| `DATABASE_URL` | asyncpg connection string from Step 1 | Secret |
| `SECRET_KEY` | any long random string (e.g. 64 random chars) | Secret |
| `GEMINI_API_KEY` | key from [aistudio.google.com](https://aistudio.google.com) | Secret |
| `ENVIRONMENT` | `production` | Variable |
| `LOG_LEVEL` | `warning` | Variable |
| `CORS_ORIGINS` | `["https://edaptv2.vercel.app"]` — update after Step 3 | Variable |

> `CORS_ORIGINS` must be a valid JSON array. Add all Vercel preview domains if needed, e.g.:
> `["https://edaptv2.vercel.app","https://edaptv2-git-main-username.vercel.app"]`

### 2c. Connect GitHub for auto-deploy

1. In your GitHub repo, go to **Settings → Secrets and variables → Actions → New repository secret** and add:

   | Secret name | Value |
   |---|---|
   | `HF_TOKEN` | A Hugging Face **write** token from [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) |
   | `HF_SPACE` | `<your-hf-username>/edaptv2-backend` |

2. Push any change to `main` that touches `backend/**` — the GitHub Actions workflow at `.github/workflows/deploy-backend-hf.yml` will automatically sync the backend code to the Space and trigger a rebuild.

3. Monitor the build in the Space's **Logs** tab. A successful start shows:
   ```
   Application startup complete.
   Uvicorn running on http://0.0.0.0:8000
   ```

### 2d. Note your backend URL

Your backend is now live at:
```
https://<hf-username>-edaptv2-backend.hf.space
```

Verify it works by opening:
```
https://<hf-username>-edaptv2-backend.hf.space/health
```
Expected response: `{"status": "ok", "version": "2.0.0"}`

---

## Step 3 — Frontend (Vercel)

### 3a. Import the project

1. Sign up at [vercel.com](https://vercel.com) with GitHub.
2. Click **New Project** → select the `EDAPTv2` repository.
3. Vercel detects `vercel.json` automatically — **do not change any build settings**.
4. Click **Deploy**.

### 3b. Set environment variables

After the first deploy, go to **Project → Settings → Environment Variables** and add:

| Key | Value | Environments |
|---|---|---|
| `REACT_APP_API_BASE_URL` | `https://<hf-username>-edaptv2-backend.hf.space` | Production, Preview, Development |

Then go to **Deployments** → select the latest → **Redeploy** to rebuild with the variable.

### 3c. Update CORS on the backend

Go back to your HF Space → **Settings** → update `CORS_ORIGINS` to include your Vercel domain:
```json
["https://edaptv2.vercel.app", "https://edaptv2-git-main-username.vercel.app"]
```

---

## Branch Preview Deployments

Every branch pushed to GitHub gets its own Vercel preview URL automatically. No manual steps required after initial setup.

| Branch | Frontend URL |
|---|---|
| `main` | `https://edaptv2.vercel.app` |
| `role_based_acl` | `https://edaptv2-git-role-based-acl-username.vercel.app` |
| `any-feature` | `https://edaptv2-git-any-feature-username.vercel.app` |

All preview branches share the same backend (HF Spaces) and database (Neon). Share the Vercel URL for each branch when demoing progress to stakeholders.

---

## Local Development

Local development still uses Docker Compose and is unaffected by the cloud deployment.

```bash
# Copy the example env file and fill in your values
cp ".env copy.example" .env

# Start all services (PostgreSQL, FastAPI, React, pgAdmin)
docker compose up --build
```

| Service | Local URL |
|---|---|
| React frontend | http://localhost:3000 |
| FastAPI backend | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| pgAdmin | http://localhost:5050 |

---

## Environment Variables Reference

### Backend (set in HF Spaces Secrets)

| Variable | Description | Example |
|---|---|---|
| `DATABASE_URL` | PostgreSQL async DSN | `postgresql+asyncpg://user:pass@host/db` |
| `SECRET_KEY` | JWT signing key | 64-char random string |
| `GEMINI_API_KEY` | Google Gemini API key | `AIza...` |
| `ENVIRONMENT` | Runtime mode | `production` |
| `LOG_LEVEL` | Logging verbosity | `warning` |
| `CORS_ORIGINS` | Allowed frontend origins (JSON array) | `["https://edaptv2.vercel.app"]` |

### Frontend (set in Vercel Environment Variables)

| Variable | Description | Example |
|---|---|---|
| `REACT_APP_API_BASE_URL` | Backend base URL | `https://username-edaptv2-backend.hf.space` |

---

## Troubleshooting

### "Registration failed" / "Cannot reach the server"

The frontend cannot connect to the backend. Check in order:

1. **Open browser DevTools → Network tab** and retry the action. Look at the failed request URL.
2. If the URL is `http://localhost:8000/...` → `REACT_APP_API_BASE_URL` is not set in Vercel.
3. If the request is blocked by CORS → `CORS_ORIGINS` on the backend does not include your Vercel domain.
4. If the request times out → the HF Space may be sleeping; wait 30 seconds and retry.

### Backend not starting on HF Spaces

Check the Space's **Logs** tab for errors. Common causes:

- `DATABASE_URL` secret is missing or malformed — must use `postgresql+asyncpg://` prefix.
- `SECRET_KEY` is not set.
- `GEMINI_API_KEY` is invalid or missing (the app starts but AI Engine routes will fail).

### GitHub Action not triggering

- Confirm `HF_TOKEN` and `HF_SPACE` are set in **GitHub → Settings → Secrets → Actions**.
- The workflow only triggers on pushes to `main` that change files inside `backend/`. Push a trivial change to `backend/` to force a deploy.
- Check the **Actions** tab in GitHub for run logs.

### Build fails on Vercel (ESLint errors)

Vercel sets `CI=true` which treats ESLint warnings as errors. Fix any `no-unused-vars` warnings locally before pushing:

```bash
cd frontend
npm run build
```

Any ESLint errors that would fail the Vercel build will also fail this local command.

---

## Architecture Diagram

```
Browser
  │
  ▼
Vercel (Static CDN)
  React SPA — branch-specific build
  │
  │  HTTPS API calls
  ▼
Hugging Face Spaces (Docker)
  FastAPI + Gunicorn
  JWT auth · ML predictions · Gemini AI
  │
  │  asyncpg
  ▼
Neon.tech (Serverless PostgreSQL)
  Tables auto-created on first boot
```

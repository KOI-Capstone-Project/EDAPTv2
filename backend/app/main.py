# EDAPT v2 Backend — King's Own Institute Capstone 2026.
# For production deployment see SECURITY.md for known limitations and required infrastructure changes.

"""
EDAPT v2 — FastAPI Backend (self-contained)

Auth: PostgreSQL User table + bcrypt + JWT.
Data: CSV loaded into _DATA (pandas DataFrame) via POST /api/ingest.
Dashboard: 8 endpoints that slice _DATA by role + query filters.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
import hashlib
import io
import json
import logging
import math
import os
from pathlib import Path

import secrets
import smtplib
import uuid
from typing import Annotated, Optional

import joblib
import pandas as pd
from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Query, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field, StringConstraints, field_validator
from sqlalchemy import delete, desc, func, select, text as sa_text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import AnalyzeJob, ApiKey, AuditLog, Base, IngestJob, Intervention, OAuthProviderConfig, PendingIngest, Prediction, RiskEmailTemplate, User as UserModel
from app import oauth_providers
# Light module — pure functions over an already-computed SHAP dict, no model
# loading, so it is safe to import at module scope unlike app.ml.predictor.
from app.ml.actionable import excluded_factor_summary, top_actionable_factor
import contextlib

load_dotenv()

# ── Logging ──────────────────────────────────────────────────────────────────
# Startup and lifecycle diagnostics go through the logging module, not print().
# print() writes unconditionally to stdout with no level, no timestamp and no
# way to filter it — so in production every message was emitted at the same
# volume whether it was "model loaded" or "model FAILED to load", and LOG_LEVEL
# (already passed to uvicorn in docker-compose) had no effect on any of it.
# The CLI scripts under app/ml/ deliberately keep using print(): their output IS
# the deliverable of an interactive command, not server diagnostics.
LOG_LEVEL = os.getenv("LOG_LEVEL", "info").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("edapt")


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SECRET_KEY:           str       = os.getenv("SECRET_KEY", "edapt-dev-secret-key-change-in-production")
if SECRET_KEY == "edapt-dev-secret-key-change-in-production":
    logger.warning(
        "SECRET_KEY is set to the insecure default dev value — "
        "set a strong SECRET_KEY env var before deploying"
    )
ALGORITHM:            str       = "HS256"
TOKEN_EXPIRE_MINUTES: int       = 480
CORS_ORIGINS:         list[str] = [
    "http://localhost:3000",    "http://localhost:5173",
    "http://localhost:80",      "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]
GMAIL_SENDER:         str       = os.getenv("GMAIL_SENDER", "")
GMAIL_APP_PASSWORD:   str       = os.getenv("GMAIL_APP_PASSWORD", "")
MAX_ATTEMPTS:         int       = 5
LOCKOUT_MINUTES:      int       = 15
OTP_EXPIRY_MINUTES:   int       = 10
MAX_UPLOAD_BYTES:     int       = 50 * 1024 * 1024
# Attendance is recorded per class session, not per assessment — the real
# attendance file is ~119MB uncompressed (2.5M rows) vs. the capstone file's
# ~36MB (327K rows) for the same population, so it needs its own, higher cap
# rather than sharing the capstone upload's 50MB limit. This cap applies to
# what a user UPLOADS (a plain CSV); the checked-in copy is stored gzipped
# (masked_attendance.csv.gz, ~9MB) and read directly by pandas.
MAX_ATTENDANCE_UPLOAD_BYTES: int = 200 * 1024 * 1024

# ── ML model (loaded once at startup) ────────────────────────────────────────

_ML_DIR:         Path            = Path(__file__).parent / "ml"
_MODEL_NAME:      str            = "Random Forest"
_MODEL_ACCURACY:  float          = 0.0
_SAFE_SUBJECTS:   list[str]      = []

try:
    _model_package    = joblib.load(_ML_DIR / "best_model.pkl")
    _MODEL_NAME       = _model_package.get("model_name", "Random Forest")
    _MODEL_ACCURACY   = _model_package.get("accuracy", 0.0)
    _SAFE_SUBJECTS    = _model_package.get("safe_subjects", [])
    logger.info("ML model loaded: %s (accuracy %.4f, %d safe subjects)",
                _MODEL_NAME, _MODEL_ACCURACY, len(_SAFE_SUBJECTS))
except Exception as _e:
    logger.warning("ML model not loaded — %s. Run train_model.py first.", _e)

# ── Subject reliability (loaded once at startup) ─────────────────────────────

_RELIABILITY_PATH = Path(__file__).parent.parent.parent / "data" / "subject_reliability.json"
_SUBJECT_RELIABILITY: dict = {"fully_clean": [], "mostly_clean": [], "unreliable": []}

try:
    with open(_RELIABILITY_PATH) as _f:
        _SUBJECT_RELIABILITY = json.load(_f)
except Exception as _e:
    logger.warning("subject_reliability.json not loaded — %s", _e)


def _subject_reliability_category(subject: str) -> str:
    """Classify a subject as fully_clean / mostly_clean / unreliable per subject_reliability.json.

    Subjects absent from all three lists default to unreliable — no evidence of
    data quality means predictions should not be served for them.
    """
    if subject in _SUBJECT_RELIABILITY.get("fully_clean", []):
        return "fully_clean"
    if subject in _SUBJECT_RELIABILITY.get("mostly_clean", []):
        return "mostly_clean"
    return "unreliable"


_attendance_raw_sessions_cache: dict = {}


def _attendance_raw_sessions() -> pd.DataFrame:
    """Raw (non-aggregated) attendance sessions for the roster endpoint's
    mid-term truncation — reuses train_model.load_attendance_raw() rather
    than re-implementing the same filter/join logic. Cached against the
    current _DATA's identity so ingestion (which replaces _DATA wholesale)
    correctly invalidates it."""
    from app.ml.train_model import load_attendance_raw
    cache_key = id(_DATA)
    if cache_key not in _attendance_raw_sessions_cache:
        _attendance_raw_sessions_cache.clear()
        _attendance_raw_sessions_cache[cache_key] = load_attendance_raw(_DATA).sort_values(
            ["class_no", "actv_no", "cls_session_no"]
        )
    return _attendance_raw_sessions_cache[cache_key]


def _truncated_attendance_rate(student_id: str, subject: str, study_period: str, coverage_fraction: float) -> Optional[float]:
    """Real attendance rate truncated to the SAME coverage fraction as a
    student's currently-recorded marks — the roster-endpoint equivalent of
    build_simulated_progress_features()'s truncation, so a genuinely
    mid-term roster row is never scored against that student's full/final
    attendance (the same leakage class as the mid-term 100%-accuracy
    incident this project already caught once). Returns None if this
    student has no attendance sessions at all (rare — build_attendance_features.py
    found a 100% match rate on the current dataset, but not guaranteed for
    every future ingested file)."""
    sessions = _attendance_raw_sessions()
    mask = (
        (sessions["STUDENTID_MASKED"] == student_id)
        & (sessions["SUBJECTCODE"] == subject)
        & (sessions["STUDYPERIOD"] == study_period)
    )
    codes = sessions.loc[mask, "attendance_code"].values
    if len(codes) == 0:
        return None
    n_included = round(coverage_fraction * len(codes))
    truncated = codes[:n_included]
    if len(truncated) == 0:
        return None
    return float((truncated == "H").mean())


def _subject_average_attendance_rate(subject: str) -> Optional[float]:
    """Real average ATTENDANCE_RATE for a subject, from _ATTENDANCE (the same
    build_attendance_features() output loaded at startup) — used as the
    What-If Simulator's default when a lecturer leaves attendance blank,
    per the explicit instruction not to require it on every hypothetical
    scenario. Returns None if no attendance data is loaded/matches (the
    caller must treat that as "no default available", not a silent 0)."""
    if _ATTENDANCE is None or _ATTENDANCE.empty or "ATTENDANCE_RATE" not in _ATTENDANCE.columns:
        return None
    subj_rows = _ATTENDANCE[_ATTENDANCE["SUBJECTCODE"] == subject]
    if subj_rows.empty:
        return None
    return float(subj_rows["ATTENDANCE_RATE"].mean())


def _student_full_attendance_rate(student_id: str, subject: str, study_period: str) -> Optional[float]:
    """This enrolment's real, full-term ATTENDANCE_RATE from _ATTENDANCE — the
    complete-record counterpart to _truncated_attendance_rate. Safe only for a
    complete record (the same closed-snapshot premise build_early_features()
    relies on). Returns None if this enrolment has no attendance row at all."""
    if _ATTENDANCE is None or _ATTENDANCE.empty or "ATTENDANCE_RATE" not in _ATTENDANCE.columns:
        return None
    match = _ATTENDANCE[
        (_ATTENDANCE["STUDENTID_MASKED"] == student_id)
        & (_ATTENDANCE["SUBJECTCODE"] == subject)
        & (_ATTENDANCE["STUDYPERIOD"] == study_period)
    ]
    if match.empty:
        return None
    return float(match["ATTENDANCE_RATE"].iloc[0])


def _resolve_attendance_rate(
    student_id:        Optional[str],
    subject:           str,
    study_period:      str,
    coverage_fraction: Optional[float] = None,
) -> tuple[Optional[float], bool]:
    """THE single source of truth for "what attendance rate does this prediction use?"

    Both /api/predict and /api/subjects/{subject}/roster resolve attendance
    through this one function. They previously each did their own lookup, and
    they drifted: the roster used a real student's own rate while /api/predict
    fell back to the subject average for that same student, so the same person
    got two different attendance values depending on which endpoint was called
    (same class of bug as the Fail/Safe risk-band contradiction). Keep this the
    only place that makes the decision.

    coverage_fraction distinguishes the two legitimate tiers, and it is NOT
    optional-by-taste — passing None for a genuinely mid-term prediction would
    feed it that student's full/final attendance, i.e. end-of-term leakage:
      - None  -> complete record: this enrolment's real full-term rate.
      - float -> mid-term: rate truncated to the same coverage fraction the
                 student's marks have reached (see _truncated_attendance_rate).

    Returns (rate, is_subject_average_default). The subject average is a genuine
    last resort, used only when this enrolment has NO attendance record at all —
    never as a substitute for a lookup that could have succeeded. On the current
    dataset 0 of 78,886 enrolments miss, so this should not fire for a real
    student; it exists for future ingested files that may not match as cleanly.
    A caller that already has an explicit rate (a What-If scenario specifying
    one) must not call this at all — that value wins outright.
    """
    rate = None
    if student_id is not None:
        if coverage_fraction is None:
            rate = _student_full_attendance_rate(str(student_id), subject, study_period)
        else:
            rate = _truncated_attendance_rate(str(student_id), subject, study_period, coverage_fraction)
    if rate is not None:
        return rate, False
    return _subject_average_attendance_rate(subject), True


def _period_total_weight(subject: str, study_period: str) -> float:
    """Total assessment weighting defined for a subject+period, de-duplicated by
    assessment type. Shared by the roster and /api/predict so both derive the
    same coverage fraction (and therefore the same mid-term attendance
    truncation) for the same enrolment."""
    if _DATA is None or _DATA.empty:
        return 0.0
    df = _DATA[(_DATA["SUBJECTCODE"] == subject) & (_DATA["STUDYPERIOD"] == study_period)]
    df = df.dropna(subset=["MARKPERCENT"])
    if df.empty:
        return 0.0
    return float(df.drop_duplicates(subset=["ASSESSMENTTYPECODE"])["WEIGHTING"].sum())

# ── Gemini ────────────────────────────────────────────────────────────────────

class ResourceExhausted(Exception):
    """Fallback stand-in used if google.api_core is unavailable at import time."""

_flash_model               = None
_pro_model                 = None
_GEMINI_TOKEN_LOG: list[dict] = []

try:
    import google.generativeai as _genai
    from google.api_core.exceptions import ResourceExhausted
    _gemini_key = os.getenv("GEMINI_API_KEY", "")
    if _gemini_key and "your-gemini" not in _gemini_key:
        _genai.configure(api_key=_gemini_key)
        _flash_model = _genai.GenerativeModel("gemini-1.5-flash")
        _pro_model   = _genai.GenerativeModel("gemini-1.5-pro")
        logger.info("Gemini API configured successfully")
    else:
        logger.warning("Gemini API key not configured")
except Exception as _e:
    logger.warning("Gemini API key not configured — %s", _e)

# ─────────────────────────────────────────────────────────────────────────────
# In-Memory State
# ─────────────────────────────────────────────────────────────────────────────

_pwd             = CryptContext(schemes=["bcrypt"], deprecated="auto")
_REVOKED_TOKENS: set[str]        = set()
_OTP_STORE:      dict[str, dict] = {}   # email → {otp, expires_at}
_FAILED_LOGINS:  dict[str, list] = {}

# ─────────────────────────────────────────────────────────────────────────────
# Password and Security Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _validate_password(password: str) -> None:
    """Enforce the 5-part password policy; raises HTTPException(400) on failure."""
    if len(password) < 10:
        raise HTTPException(400, "Password must be at least 10 characters.")
    if not any(c.isupper() for c in password):
        raise HTTPException(400, "Password must contain at least one uppercase letter.")
    if not any(c.islower() for c in password):
        raise HTTPException(400, "Password must contain at least one lowercase letter.")
    if not any(c.isdigit() for c in password):
        raise HTTPException(400, "Password must contain at least one number.")
    if not any(not c.isalnum() for c in password):
        raise HTTPException(400, "Password must contain at least one special character.")


def _check_lockout(email: str) -> None:
    """Raise HTTP 429 if the account has hit MAX_ATTEMPTS failures within LOCKOUT_MINUTES."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=LOCKOUT_MINUTES)
    recent = [t for t in _FAILED_LOGINS.get(email, []) if t > cutoff]
    _FAILED_LOGINS[email] = recent
    if len(recent) >= MAX_ATTEMPTS:
        wait = LOCKOUT_MINUTES - int(
            (datetime.now(timezone.utc) - min(recent)).total_seconds() / 60
        )
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {max(1, wait)} minute(s).",
        )


def _record_failed_attempt(email: str) -> None:
    """Append a timestamped failed-login entry for the given email."""
    _FAILED_LOGINS.setdefault(email, []).append(datetime.now(timezone.utc))

# ─────────────────────────────────────────────────────────────────────────────
# Email and OTP Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _send_otp_email(to_email: str, otp: str) -> None:
    """Send OTP via Gmail SMTP. Raises RuntimeError if email service is not configured."""
    if not GMAIL_SENDER or not GMAIL_APP_PASSWORD:
        raise RuntimeError("Email service not configured")
    msg = MIMEText(
        f"Your EDAPT password reset code is: {otp}\n\n"
        f"This code expires in {OTP_EXPIRY_MINUTES} minutes.\n\n"
        "If you did not request a password reset, you can ignore this email.",
        "plain",
    )
    msg["Subject"] = "EDAPT — Password Reset Code"
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = to_email
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_SENDER, to_email, msg.as_string())


def _generate_otp(email: str) -> str:
    """Generate a 6-digit OTP, store it in _OTP_STORE keyed by email, and return the code."""
    otp = "".join(secrets.choice("0123456789") for _ in range(6))
    _OTP_STORE[email] = {
        "otp":        otp,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES),
    }
    return otp


def _verify_otp(email: str, code: str) -> bool:
    """Verify a submitted OTP code. Deletes the entry on success; returns False on failure."""
    entry = _OTP_STORE.get(email)
    if not entry:
        return False
    if datetime.now(timezone.utc) >= entry["expires_at"]:
        return False
    if not secrets.compare_digest(entry["otp"], code):
        return False
    del _OTP_STORE[email]
    return True

# ── Data store ────────────────────────────────────────────────────────────────

# Global shared state — all roles read from this single DataFrame. Role filtering is
# applied per request in _role_filter. Head of Technology and Head of School see all
# rows; Lecturers see only rows matching their assigned subjects.
_DATA: Optional[pd.DataFrame] = pd.DataFrame()
_DATA_PATH = Path(__file__).parent.parent.parent / "data" / "Capstone_data_20260729.csv"

_ATTENDANCE: Optional[pd.DataFrame] = pd.DataFrame()
_ATTENDANCE_PATH = Path(__file__).parent.parent.parent / "data" / "masked_attendance.csv.gz"


def _current_capstone_path() -> Path:
    """Whatever capstone CSV is actually backing the live dataset right now:
    the ingested override (INGESTED_DATA_DIR/ingested_capstone.csv) if an
    admin has ever confirmed a capstone upload, else the bundled sample
    file this container started with. Used both at startup — so previously
    ingested data survives a container restart instead of reverting to the
    bundled sample (or nothing) — and by build_attendance_features's
    callers below, which used to hardcode _DATA_PATH regardless of what
    had actually been ingested (see _do_attendance_confirm)."""
    import app.ml.train_model as train_model_mod
    ingested = train_model_mod.INGESTED_DATA_DIR / "ingested_capstone.csv"
    return ingested if ingested.exists() else _DATA_PATH


def _current_attendance_path() -> Path:
    """Same idea as _current_capstone_path, for the raw attendance file:
    the ingested override (INGESTED_DATA_DIR/ingested_attendance_raw.csv)
    if an admin has ever confirmed an attendance upload, else the bundled
    sample. Without this, _ATTENDANCE silently reverted to the bundled
    sample (or nothing) on every restart, discarding previously ingested
    attendance data — the same restart-durability gap _current_capstone_path
    closes for capstone data."""
    import app.ml.train_model as train_model_mod
    ingested = train_model_mod.INGESTED_DATA_DIR / "ingested_attendance_raw.csv"
    return ingested if ingested.exists() else _ATTENDANCE_PATH


def _load_capstone_dataframe(path: Path) -> pd.DataFrame:
    """Parse+clean one capstone CSV into the shape _DATA expects — shared
    by the startup load below and by DELETE /api/ingest/datasets/{kind},
    which needs to reload _DATA from whatever's left (the bundled sample,
    or nothing) exactly the same way startup does."""
    _df = pd.read_csv(path)
    _df.columns = [c.strip() for c in _df.columns]
    if "MARKPERCENT" in _df.columns:
        _df["MARKPERCENT"] = pd.to_numeric(_df["MARKPERCENT"], errors="coerce")
        _df["PASSED"] = _df["MARKPERCENT"] >= 50
    if "STUDYPERIOD" in _df.columns:
        _df["STUDYPERIOD"] = _df["STUDYPERIOD"].apply(
            lambda x: str(round(float(x), 1)) if pd.notna(x) else ""
        )
    return _df


def _load_attendance_dataframe() -> pd.DataFrame:
    """Rebuild _ATTENDANCE from whatever's currently on disk (ingested
    override or bundled sample, via _current_attendance_path/
    _current_capstone_path) — shared by the startup load below and by
    DELETE /api/ingest/datasets/{kind}. Depends on _DATA already being
    the dataframe you want the PASS target merged from — call this AFTER
    _DATA is set to whatever it should be."""
    from app.ml.train_model import collapse_attempts_to_latest_per_type, build_target
    from app.ml.build_attendance_features import build_attendance_features

    att_features = build_attendance_features(
        attendance_path=_current_attendance_path(), capstone_path=_current_capstone_path()
    )
    if not _DATA.empty:
        collapsed = collapse_attempts_to_latest_per_type(_DATA.copy())
        target = build_target(collapsed)
        att_features = att_features.merge(
            target, on=["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"], how="left"
        )
    return att_features


# Load the bundled sample, or whatever was last ingested via the UI, on
# server start — so a real deployment's already-uploaded data survives a
# restart instead of reverting to the bundled demo file (or nothing at
# all). The /api/ingest endpoint handles runtime uploads and overwrites
# _DATA from then on, for the lifetime of this process.
try:
    _DATA = _load_capstone_dataframe(_current_capstone_path())
    logger.info("Startup data loaded: %s rows, %d columns", f"{len(_DATA):,}", len(_DATA.columns))
except FileNotFoundError:
    logger.error("Startup CSV not found at %s — upload a dataset via /api/ingest", _current_capstone_path())
except Exception as _e:
    logger.error("Failed to load startup data: %s", _e)


# ── Attendance data store ───────────────────────────────────────────────────
# Wired in as a standard part of startup, same as _DATA above — not a manual
# script someone has to remember to run before attendance endpoints work. One
# row per (STUDENTID_MASKED, SUBJECTCODE, STUDYPERIOD) enrolment, with the
# same real PASS target training uses (via collapse_attempts_to_latest_per_type
# + build_target, not the row-level PASSED column _DATA uses) merged on, so
# an attendance-vs-outcome correlation means the same "pass" everywhere else
# in this project means.
try:
    _ATTENDANCE = _load_attendance_dataframe()
    logger.info("Attendance features loaded: %s enrolments", f"{len(_ATTENDANCE):,}")
except FileNotFoundError:
    logger.warning("Attendance data not found at %s — attendance endpoints will return empty", _current_attendance_path())
except Exception as _e:
    logger.error("Failed to load attendance data: %s", _e)

# ── Database setup ────────────────────────────────────────────────────────────

_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://sangamgurung@localhost:5432/edapt",
)
_engine       = create_async_engine(_DB_URL, echo=False, pool_pre_ping=True)
_AsyncSession = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    """Yield an async database session with automatic commit/rollback."""
    async with _AsyncSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _append_audit_db(
    db: AsyncSession,
    *,
    user_uid: str,
    action_type: str,
    status: str,
    detail: str,
) -> None:
    """Write a single audit-log row to PostgreSQL and commit immediately."""
    db.add(AuditLog(user_uid=user_uid, action_type=action_type, status=status, detail=detail))
    await db.commit()


async def _upsert_prediction(
    db: AsyncSession,
    *,
    student_id_masked: str,
    subject_code:       str,
    study_period:        str,
    result:              dict,
    commit:              bool = True,
) -> None:
    """
    Record a prediction for a real, identified student so it can later be
    reconciled against the real outcome (reconcile_predictions.py) and rolled
    into an accuracy report (prediction_accuracy_report.py).

    Upserts on (student_id_masked, subject_code, study_period, model_version)
    — the same natural key the unique constraint enforces — so re-predicting
    the same student under the same model version (e.g. reopening a roster
    page) refreshes the stored prediction rather than accumulating duplicate
    history rows. The audit log already exists for a call-by-call history;
    this table is "our current prediction for this student, per model
    version," not a log.

    Silently no-ops if `result` has no model_version (e.g. the model wasn't
    loaded) — there's nothing traceable to record in that case.

    commit=False lets a caller looping over many students (the roster
    endpoint) batch every upsert into one commit at the end of the loop,
    instead of a round-trip per student.
    """
    model_version = result.get("model_version")
    if not model_version or result.get("prediction") is None:
        return

    stmt = pg_insert(Prediction).values(
        student_id_masked = student_id_masked,
        subject_code       = subject_code,
        study_period        = study_period,
        model_version       = model_version,
        predicted_pass      = result["prediction"] == "Pass",
        pass_probability    = (result["probability"] / 100) if result.get("probability") is not None else None,
        risk_band            = result.get("risk_band"),
        estimate_type        = result.get("estimate_type"),
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_prediction_student_subject_period_model",
        set_={
            "predicted_pass":   stmt.excluded.predicted_pass,
            "pass_probability": stmt.excluded.pass_probability,
            "risk_band":        stmt.excluded.risk_band,
            "estimate_type":    stmt.excluded.estimate_type,
            "predicted_at":     func.now(),
        },
    )
    await db.execute(stmt)
    if commit:
        await db.commit()


async def _seed_default_users() -> None:
    """Insert the three default demo accounts if the users table is empty."""
    async with _AsyncSession() as db:
        result = await db.execute(select(UserModel))
        if result.scalars().first() is not None:
            return
        defaults = [
            UserModel(
                email="admin",
                name="Ken Emeleus",
                hashed_password=_pwd.hash("Admin@2025!"),
                role="Head of Technology",
                is_active=True,
                is_super_admin=True,
                subjects=[],
            ),
            UserModel(
                email="user",
                name="Demo Lecturer",
                hashed_password=_pwd.hash("Lect@2025!"),
                role="Lecturer",
                is_active=True,
                is_super_admin=False,
                subjects=["ICT104", "ICT201", "ICT301"],
            ),
            UserModel(
                email="hos",
                name="Demo Head of School",
                hashed_password=_pwd.hash("HoS@2025!"),
                role="Head of School",
                is_active=True,
                is_super_admin=False,
                subjects=[],
            ),
        ]
        for u in defaults:
            db.add(u)
        await db.commit()
        logger.info("Default users seeded")


DEFAULT_RISK_EMAIL_SUBJECT = "You've been flagged as at risk in {{subject_code}}"
DEFAULT_RISK_EMAIL_BODY = (
    "Hi {{student_id}},\n\n"
    "Our early-warning system has flagged your current progress in "
    "{{subject_code}} ({{study_period}}) as \"{{risk_band}}\".\n\n"
    "We'd like to check in and see how we can help you get back on track. "
    "Please reach out to your lecturer or student support services at your "
    "earliest convenience.\n\n"
    "Kind regards,\nAcademic Support Team"
)


async def _seed_risk_email_template() -> None:
    """Insert the default Students-at-Risk email template if it's missing."""
    async with _AsyncSession() as db:
        existing = await db.get(RiskEmailTemplate, 1)
        if existing is not None:
            return
        db.add(RiskEmailTemplate(
            id=1, subject=DEFAULT_RISK_EMAIL_SUBJECT, body=DEFAULT_RISK_EMAIL_BODY,
        ))
        await db.commit()


# provider -> (env var holding its client_id, env var holding its tenant id or None)
_OAUTH_PROVIDER_ENV = {
    "google":    ("GOOGLE_CLIENT_ID", None),
    "microsoft": ("MICROSOFT_CLIENT_ID", "MICROSOFT_TENANT_ID"),
}


async def _seed_oauth_provider_configs() -> None:
    """Insert the Google/Microsoft config rows if missing, one-time-seeded
    from whatever GOOGLE_CLIENT_ID/MICROSOFT_CLIENT_ID/MICROSOFT_TENANT_ID
    env vars are already set — so a deployment that had them configured the
    old way keeps working after this migration, with nothing to re-enter
    beyond what Settings > OAuth Providers already shows. A fresh
    deployment with no env vars seeds both providers disabled and empty,
    ready to be filled in from that same page instead of a redeploy."""
    async with _AsyncSession() as db:
        for provider, (client_env, tenant_env) in _OAUTH_PROVIDER_ENV.items():
            if await db.get(OAuthProviderConfig, provider) is not None:
                continue
            client_id = os.getenv(client_env, "") or ""
            tenant_id = os.getenv(tenant_env) if tenant_env else None
            db.add(OAuthProviderConfig(
                provider=provider, client_id=client_id, tenant_id=tenant_id,
                enabled=bool(client_id),
            ))
        await db.commit()

# ── Dashboard constants ───────────────────────────────────────────────────────

PERIODS_ORDER = ["23.1", "23.2", "23.3", "24.1", "24.2", "24.3", "25.1", "25.2", "25.3"]

GRADE_BANDS = [
    ("0-10",    0,   10),
    ("11-20",  11,   20),
    ("21-30",  21,   30),
    ("31-40",  31,   40),
    ("41-50",  41,   50),
    ("51-60",  51,   60),
    ("61-70",  61,   70),
    ("71-80",  71,   80),
    ("81-90",  81,   90),
    ("91-100", 91, 9999),
]

YEAR_TO_PERIODS = {
    "2023": ["23.1", "23.2", "23.3"],
    "2024": ["24.1", "24.2", "24.3"],
    "2025": ["25.1", "25.2", "25.3"],
}

# ── Dashboard helpers ─────────────────────────────────────────────────────────

def _prev_period(period: str) -> Optional[str]:
    """Return the period immediately before the given one, or None if it is the earliest."""
    try:
        idx = PERIODS_ORDER.index(str(period))
        return PERIODS_ORDER[idx - 1] if idx > 0 else None
    except ValueError:
        return None


def _role_filter(df: pd.DataFrame, user: dict) -> pd.DataFrame:
    """Restrict rows to the lecturer's subjects. Head of Technology and Head of School see all rows."""
    if user.get("role") == "Lecturer":
        subjects = user.get("subjects", [])
        if subjects and "SUBJECTCODE" in df.columns:
            df = df[df["SUBJECTCODE"].isin(subjects)]
    return df


def _query_filter(
    df: pd.DataFrame,
    subject:    Optional[str] = None,
    trimester:  Optional[str] = None,
    year:       Optional[str] = None,
    classgroup: Optional[str] = None,
) -> pd.DataFrame:
    """Apply URL query-param filters on top of role filtering."""
    if trimester:
        df = df[df["STUDYPERIOD"] == str(trimester)]
    elif year and year in YEAR_TO_PERIODS:
        df = df[df["STUDYPERIOD"].isin(YEAR_TO_PERIODS[year])]
    if subject and "SUBJECTCODE" in df.columns:
        df = df[df["SUBJECTCODE"] == subject]
    if classgroup and "CLASSGROUP" in df.columns:
        df = df[df["CLASSGROUP"] == classgroup]
    return df


def _safe(val) -> Optional[float]:
    """Convert NaN / inf to None so JSON serialisation never breaks."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None

# ─────────────────────────────────────────────────────────────────────────────
# JWT Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _create_token(payload: dict) -> str:
    """Encode a JWT with an expiry field appended to the payload."""
    data = payload.copy()
    data["exp"] = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def _decode_token(token: str) -> dict:
    """Decode and verify a JWT; raises JWTError on invalid or expired tokens."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────────────────────────────────────

# Strict email pattern: localpart@domain.extension (extension ≥ 2 chars)
_EMAIL_REGEX = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z0-9]{2,}$'


class LoginRequest(BaseModel):
    # Accepts both email addresses and plain staff IDs (e.g. "admin").
    # Pattern blocks unsafe characters without requiring full email format.
    email:    str = Field(..., max_length=254, pattern=r'^[a-zA-Z0-9._%+@\-]+$')
    password: str = Field(..., max_length=128)


class OAuthLoginRequest(BaseModel):
    # Raw ID token as returned by the provider's own JS SDK — verified
    # server-side before it's trusted for anything.
    id_token: str = Field(..., max_length=4096)


class CreateUserRequest(BaseModel):
    email:    str = Field(..., max_length=254, pattern=_EMAIL_REGEX)
    password: str
    name:     Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    role:     str       = "Lecturer"
    subjects: list[str] = []

    @field_validator('email', mode='before')
    @classmethod
    def normalise_email(cls, v):
        if isinstance(v, str):
            return v.lower().strip()
        return v


class _AssessmentEntry(BaseModel):
    type:         str
    mark_percent: float = Field(..., ge=0.0, le=100.0)
    weighting:    float = Field(..., ge=0.0, le=100.0)


class PredictRequest(BaseModel):
    # Optional — /api/predict is used for both genuine what-if scenarios
    # (hypothetical marks, no real student) and real predictions for an
    # identified student. Only the latter gets logged to the predictions
    # table (see _upsert_prediction); a what-if call with no student_id
    # correctly logs nothing, since there's no real student to reconcile
    # a hypothetical prediction against.
    student_id:              Optional[str] = Field(None, max_length=50)
    subject:                 str   = Field(..., min_length=1, max_length=20)
    study_period:            str   = Field(..., min_length=1, max_length=10)
    trimester_num:           float
    assess1_mark:            float = Field(..., ge=0.0, le=100.0)
    assess1_weight:          float = Field(..., ge=0.0, le=100.0)
    assess1_contribution:    float = Field(..., ge=0.0, le=100.0)
    assess2_mark:            float = Field(0.0,  ge=0.0, le=100.0)
    assess2_weight:          float = Field(0.0,  ge=0.0, le=100.0)
    assess2_contribution:    float = Field(0.0,  ge=0.0, le=100.0)
    # Accepted for backward compatibility but never trusted — /api/predict
    # recomputes both server-side from assessments_used (see compute_partial_score).
    partial_weighted_score:  float = Field(..., ge=0.0, le=100.0)
    partial_weight_coverage: float = Field(..., ge=0.0, le=1.0)
    num_assessments:         int   = Field(..., ge=1)
    total_weight_recorded:   float = Field(..., ge=0.0, le=100.0)
    weight_complete:         bool  = True
    assessments_used:        list[_AssessmentEntry]
    # Optional — if omitted (What-If left blank, or an older client), the
    # handler below fills in that subject's real average ATTENDANCE_RATE
    # server-side and reports attendance_rate_is_default=true in the
    # response, rather than silently defaulting to 0 or requiring every
    # caller to always supply a value.
    attendance_rate:         Optional[float] = Field(None, ge=0.0, le=1.0)


class CreateApiKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class ApiPredictAssessment(BaseModel):
    type:         str   = Field(..., max_length=60)
    mark_percent: float = Field(..., ge=0.0, le=100.0)
    weighting:    float = Field(..., ge=0.0, le=100.0)


class ApiPredictRequest(BaseModel):
    # Public contract for the external /api/v1/predict endpoint. Deliberately
    # separate from PredictRequest above: an external caller has no reason to
    # know this project's internal "top-2-by-weight" convention, so this model
    # only accepts the raw assessment list and attendance percentage — the
    # handler derives assess1/assess2 itself via predictor._top2_by_weight.
    subject:               str   = Field(..., min_length=1, max_length=20)
    study_period:          str   = Field(..., min_length=1, max_length=10)
    trimester_num:         float
    assessments:           list[ApiPredictAssessment] = Field(..., min_length=1)
    attendance_percentage: float = Field(..., ge=0.0, le=100.0)


class GeminiAlertRequest(BaseModel):
    subject:   Optional[str] = Field(None, max_length=20)
    trimester: Optional[str] = Field(None, max_length=10)


class GeminiAnalyseRequest(BaseModel):
    subject:   str           = Field(..., max_length=20)
    trimester: Optional[str] = Field(None, max_length=10)


class GeminiAskRequest(BaseModel):
    # 500 was sized for a human typing a free-text question. Once the
    # frontend started embedding real SHAP factor lists (see PredictorView.jsx
    # fetchDetailGeminiInsight/fetchWhatIfGeminiInsight) the auto-generated
    # per-prediction question routinely exceeded that — verified: every real
    # prediction's insight request 422'd, silently degrading to the generic
    # "unavailable" fallback. 700 gives real margin for the templated
    # SHAP-factors question (~350-450 chars typical) while still bounding a
    # human-typed question to something reasonable.
    question:  str           = Field(..., max_length=700)
    subject:   Optional[str] = Field(None, max_length=20)
    trimester: Optional[str] = Field(None, max_length=10)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password:     str


class UpdateUserRequest(BaseModel):
    subjects: Optional[list[str]] = None
    active:   Optional[bool]      = None


class UpdateProfileRequest(BaseModel):
    name:       Optional[str] = None
    phone:      Optional[str] = None
    department: Optional[str] = None
    bio:        Optional[str] = None


class GeminiInstitutionAskRequest(BaseModel):
    question: str = Field(..., max_length=500)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., max_length=254, pattern=_EMAIL_REGEX)


class ResetPasswordRequest(BaseModel):
    email:        str = Field(..., max_length=254, pattern=_EMAIL_REGEX)
    otp:          str = Field(..., min_length=6, max_length=6)
    new_password: str

# ─────────────────────────────────────────────────────────────────────────────
# FastAPI App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="EDAPT v2 API", version="2.0.0")


@app.on_event("startup")
async def _startup():
    """Create database tables and seed default users on first run."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _seed_default_users()
    await _seed_risk_email_template()
    await _seed_oauth_provider_configs()
    logger.info("Database ready")
    if GMAIL_SENDER and GMAIL_APP_PASSWORD:
        logger.info("Email service configured")
    else:
        logger.warning("Email service not configured — forgot password will not work")

# ─────────────────────────────────────────────────────────────────────────────
# Middleware
# ─────────────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# ─────────────────────────────────────────────────────────────────────────────
# Role Dependencies
# ─────────────────────────────────────────────────────────────────────────────

async def get_current_user(token: str = Depends(_oauth2)) -> dict:
    """Decode JWT and return the payload dict; raises 401 if revoked or invalid."""
    if token in _REVOKED_TOKENS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = _decode_token(token)
        if "sub" not in payload:
            raise ValueError
        return payload
    except (JWTError, ValueError):
        # `from None` deliberately: the underlying JWT error (expired vs.
        # malformed vs. bad signature) must not reach the client, and chaining
        # it would put it in the traceback of an auth failure.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Restrict access to Head of Technology only."""
    if user.get("role") != "Head of Technology":
        raise HTTPException(403, "Only Head of Technology can access this feature.")
    return user


async def require_head_of_school(user: dict = Depends(get_current_user)) -> dict:
    """Restrict access to Head of Technology or Head of School."""
    if user.get("role") not in {"Head of Technology", "Head of School"}:
        raise HTTPException(
            403, "Only Head of Technology or Head of School can access this feature."
        )
    return user


async def require_super_admin(user: dict = Depends(get_current_user)) -> dict:
    """Restrict access to the system administrator (is_super_admin=True in JWT)."""
    if user.get("is_super_admin") is not True:
        raise HTTPException(403, "Only the system administrator can access this feature.")
    return user


_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    raw_key: Optional[str] = Depends(_api_key_header),
    db:      AsyncSession  = Depends(get_db),
) -> ApiKey:
    """Authenticate an external caller of /api/v1/predict via API key.

    A separate credential type from the session JWT above: API keys are
    long-lived and issued by an admin for a third-party system, not a
    logged-in human, so they get their own header and their own DB-backed
    lookup rather than being minted as another JWT.
    """
    if not raw_key:
        raise HTTPException(401, "Missing X-API-Key header.")
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    row = (await db.execute(select(ApiKey).where(ApiKey.hashed_key == key_hash))).scalar_one_or_none()
    if row is None or row.revoked:
        raise HTTPException(401, "Invalid or revoked API key.")
    row.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    return row

# ─────────────────────────────────────────────────────────────────────────────
# Auth Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health():
    """Basic liveness probe."""
    return {"status": "ok", "version": "2.0.0"}


@app.get("/api/health", tags=["Health"])
async def api_health(response: Response, db: AsyncSession = Depends(get_db)):
    """READINESS probe — can this instance actually serve a prediction right now?

    Distinct from /health above, which is pure liveness (is the process up?).
    This returns HTTP 503 when any dependency required to serve real traffic is
    missing, so a Docker HEALTHCHECK or an orchestrator can act on it. The
    previous version of this endpoint returned {"status": "ok"} unconditionally
    and would have reported healthy with no database, no data and no model.

    Each dependency is reported individually rather than collapsed into one
    boolean, so an unhealthy response says WHICH dependency is down.
    """
    from app.ml import predictor

    checks: dict[str, dict] = {}

    # 1. Database reachable — a real round-trip, not "the engine object exists".
    try:
        await db.execute(sa_text("SELECT 1"))
        checks["database"] = {"ok": True}
    except Exception as exc:
        checks["database"] = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}

    # 2. Assessment dataset loaded. Row count > 0 specifically — an empty
    #    DataFrame loads without raising but cannot serve a roster.
    rows = len(_DATA) if _DATA is not None else 0
    checks["dataset"] = {"ok": rows > 0, "rows": rows}

    # 3. Attendance features loaded. ATTENDANCE_RATE is a required feature of
    #    both live models, so without this every prediction returns an error.
    att_rows = len(_ATTENDANCE) if _ATTENDANCE is not None else 0
    checks["attendance"] = {"ok": att_rows > 0, "enrolments": att_rows}

    # 4. A live model registered AND loaded for BOTH families. The mid-term
    #    family is checked separately on purpose — it was silently broken once
    #    while the complete-record model was fine.
    checks["model_complete_record"] = {
        "ok": predictor._PACKAGE is not None,
        "version": predictor.LIVE_MODEL_VERSION,
    }
    checks["model_midterm"] = {
        "ok": predictor._SIM_PACKAGE is not None,
        "version": predictor.SIM_MODEL_VERSION,
    }

    healthy = all(c["ok"] for c in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status":  "ok" if healthy else "unhealthy",
        "version": "2.0.0",
        "checks":  checks,
        # Retained so any existing caller of the old shape keeps working.
        "rows":    rows,
        "message": "EDAPT API running" if healthy else "EDAPT API not ready to serve",
    }


def _build_login_response(db_user: UserModel) -> dict:
    subjects       = db_user.subjects or []
    is_super_admin = bool(db_user.is_super_admin)
    token = _create_token({
        "sub":            db_user.email,
        "role":           db_user.role,
        "name":           db_user.name,
        "subjects":       subjects,
        "is_super_admin": is_super_admin,
    })
    return {
        "access_token": token,
        "token_type":   "bearer",
        "user": {
            "email":          db_user.email,
            "name":           db_user.name,
            "role":           db_user.role,
            "subjects":       subjects,
            "is_super_admin": is_super_admin,
        },
    }


@app.post("/api/auth/login", tags=["Auth"])
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate a staff member and return a signed JWT."""
    _check_lockout(req.email)
    result  = await db.execute(select(UserModel).where(UserModel.email == req.email))
    db_user = result.scalar_one_or_none()

    if not db_user or not _pwd.verify(req.password, db_user.hashed_password):
        _record_failed_attempt(req.email)
        await _append_audit_db(db, user_uid=req.email, action_type="Login Failed",
                               status="Alert", detail="Invalid credentials")
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not db_user.is_active:
        raise HTTPException(
            status_code=403, detail="Account is deactivated. Contact your administrator."
        )

    _FAILED_LOGINS.pop(req.email, None)
    await _append_audit_db(db, user_uid=db_user.email, action_type="Login",
                           status="Success", detail=f"Successful login as {db_user.role}")
    return _build_login_response(db_user)


async def _complete_oauth_login(db: AsyncSession, email: str, provider: str) -> dict:
    """
    Map a verified OAuth email onto an existing EDAPT account.

    Deliberately invite-only, same as password login: a Google/Microsoft
    sign-in never creates a new user row on its own — an admin must have
    already provisioned the account via /api/users. This keeps the single
    `users` table and its role/subject assignments as the one source of
    truth for who can access what, regardless of how they authenticate.
    """
    result  = await db.execute(select(UserModel).where(UserModel.email == email))
    db_user = result.scalar_one_or_none()

    if not db_user:
        await _append_audit_db(db, user_uid=email, action_type="Login Failed",
                               status="Alert", detail=f"No account for {provider} sign-in")
        raise HTTPException(
            status_code=403,
            detail="No EDAPT account is registered for this email. Ask an administrator to create one first.",
        )

    if not db_user.is_active:
        raise HTTPException(
            status_code=403, detail="Account is deactivated. Contact your administrator."
        )

    await _append_audit_db(db, user_uid=db_user.email, action_type="Login",
                           status="Success", detail=f"Successful login as {db_user.role} via {provider}")
    return _build_login_response(db_user)


@app.post("/api/auth/google", tags=["Auth"])
async def login_google(req: OAuthLoginRequest, db: AsyncSession = Depends(get_db)):
    """Sign in with a Google-verified ID token. client_id comes from the
    Settings > OAuth Providers config (see OAuthProviderConfig), not an env
    var — a disabled or unfilled-in provider means no client_id is passed,
    same as it being unset used to."""
    cfg = await db.get(OAuthProviderConfig, "google")
    client_id = cfg.client_id if (cfg and cfg.enabled) else None
    try:
        email = oauth_providers.verify_google_id_token(req.id_token, client_id)
    except oauth_providers.OAuthVerificationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return await _complete_oauth_login(db, email, provider="Google")


@app.post("/api/auth/microsoft", tags=["Auth"])
async def login_microsoft(req: OAuthLoginRequest, db: AsyncSession = Depends(get_db)):
    """Sign in with a Microsoft-verified ID token. client_id/tenant_id come
    from the Settings > OAuth Providers config, same reasoning as Google above."""
    cfg = await db.get(OAuthProviderConfig, "microsoft")
    client_id = cfg.client_id if (cfg and cfg.enabled) else None
    tenant_id = cfg.tenant_id if cfg else None
    try:
        email = await oauth_providers.verify_microsoft_id_token(req.id_token, client_id, tenant_id)
    except oauth_providers.OAuthVerificationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return await _complete_oauth_login(db, email, provider="Microsoft")


class OAuthProviderUpdate(BaseModel):
    client_id: str       = Field("", max_length=255)
    tenant_id: str | None = Field(None, max_length=255)
    enabled:   bool      = False


def _oauth_provider_public_dict(row: OAuthProviderConfig | None, provider: str) -> dict:
    return {
        "provider":   provider,
        "client_id":  row.client_id if row else "",
        "tenant_id":  row.tenant_id if row else None,
        "enabled":    bool(row.enabled) if row else False,
        "updated_by": row.updated_by if row else None,
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
    }


@app.get("/api/oauth-providers", tags=["Auth"])
async def list_oauth_providers(
    user: dict         = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """Full Google/Microsoft config, including disabled/empty rows — admin
    only, for the Settings > OAuth Providers page. Client IDs are public
    identifiers (see OAuthProviderConfig's docstring), so returning them
    to an already-authenticated admin here is no different a disclosure
    than the public endpoint below returning them to anyone."""
    rows = {r.provider: r for r in (await db.execute(select(OAuthProviderConfig))).scalars().all()}
    return {"providers": [_oauth_provider_public_dict(rows.get(p), p) for p in _OAUTH_PROVIDER_ENV]}


@app.put("/api/oauth-providers/{provider}", tags=["Auth"])
async def update_oauth_provider(
    provider: str,
    req:  OAuthProviderUpdate,
    user: dict         = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """Configure a provider's sign-in — admin only (Head of Technology /
    Head of School). This is the replacement for hand-editing
    GOOGLE_CLIENT_ID/MICROSOFT_CLIENT_ID/MICROSOFT_TENANT_ID and
    redeploying: the next login attempt reads whatever is saved here."""
    if provider not in _OAUTH_PROVIDER_ENV:
        raise HTTPException(404, f"Unknown provider '{provider}'. Expected one of: {', '.join(_OAUTH_PROVIDER_ENV)}")

    row = await db.get(OAuthProviderConfig, provider)
    if row is None:
        row = OAuthProviderConfig(provider=provider)
        db.add(row)

    client_id = req.client_id.strip()
    now = datetime.now(timezone.utc)
    row.client_id  = client_id
    row.tenant_id  = (req.tenant_id or "").strip() or None
    # Can't be enabled with no client_id to verify tokens against, regardless
    # of what the toggle in the request says.
    row.enabled    = bool(req.enabled and client_id)
    row.updated_by = user["sub"]
    row.updated_at = now

    await _append_audit_db(
        db, user_uid=user["sub"], action_type="Settings Changed", status="Success",
        detail=f"Updated the {provider} OAuth provider config",
    )
    return {
        "provider": provider, "client_id": client_id, "tenant_id": row.tenant_id,
        "enabled": row.enabled, "updated_by": user["sub"], "updated_at": now.isoformat(),
    }


@app.get("/api/oauth-providers/public", tags=["Auth"])
async def public_oauth_providers(db: AsyncSession = Depends(get_db)):
    """Unauthenticated — the login page needs this before the user has a
    token at all, to know which sign-in buttons to render and what
    client_id/tenant_id to hand each provider's own JS SDK. Only exposes
    enabled providers with a client_id set; both fields are public
    identifiers, not secrets (see OAuthProviderConfig's docstring)."""
    rows = (await db.execute(
        select(OAuthProviderConfig).where(OAuthProviderConfig.enabled.is_(True))
    )).scalars().all()
    return {
        "providers": [
            {"provider": r.provider, "client_id": r.client_id, "tenant_id": r.tenant_id}
            for r in rows if r.client_id
        ]
    }


@app.post("/api/auth/forgot-password", tags=["Auth"])
async def forgot_password(req: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Send a 6-digit OTP to the registered email; returns dev_otp when SMTP is unconfigured."""
    # Always respond with the same message to avoid user enumeration
    result  = await db.execute(select(UserModel).where(UserModel.email == req.email))
    db_user = result.scalar_one_or_none()
    if not db_user or not db_user.is_active:
        return {"message": "If an account exists for that email, a reset code has been sent."}

    otp = _generate_otp(req.email)

    try:
        _send_otp_email(req.email, otp)
        await _append_audit_db(db, user_uid=req.email, action_type="Password Reset Requested",
                               status="Success", detail="OTP sent to registered email")
    except RuntimeError:
        # Email service not configured — return OTP in response for dev/demo only
        await _append_audit_db(db, user_uid=req.email, action_type="Password Reset Requested",
                               status="Warning", detail="OTP generated but email service not configured")
        return {"message": "Email service not configured. For demo use this code.", "dev_otp": otp}
    except Exception as exc:
        await _append_audit_db(db, user_uid=req.email, action_type="Password Reset Requested",
                               status="Error", detail="Failed to send OTP email")
        raise HTTPException(500, "Failed to send reset email. Please try again later.") from exc

    return {"message": "If an account exists for that email, a reset code has been sent."}


@app.post("/api/auth/reset-password", tags=["Auth"])
async def reset_password(req: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Verify OTP and update the user's password."""
    if not _verify_otp(req.email, req.otp):
        raise HTTPException(400, "Invalid or expired reset code.")

    _validate_password(req.new_password)

    result  = await db.execute(select(UserModel).where(UserModel.email == req.email))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(404, "Account not found.")

    db_user.hashed_password = _pwd.hash(req.new_password)
    await _append_audit_db(db, user_uid=req.email, action_type="Password Reset",
                           status="Success", detail="Password successfully reset via OTP")
    return {"message": "Password reset successfully. You can now log in."}


@app.post("/api/auth/change-password", tags=["Auth"])
async def change_password(
    req:  ChangePasswordRequest,
    user: dict = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """Allow an authenticated user to change their own password."""
    email   = user.get("sub", "")
    result  = await db.execute(select(UserModel).where(UserModel.email == email))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(404, "User not found.")
    if not _pwd.verify(req.current_password, db_user.hashed_password):
        await _append_audit_db(db, user_uid=email, action_type="Password Change",
                               status="Alert", detail="Failed — incorrect current password")
        raise HTTPException(400, "Current password is incorrect.")
    _validate_password(req.new_password)
    db_user.hashed_password = _pwd.hash(req.new_password)
    await _append_audit_db(db, user_uid=email, action_type="Password Change",
                           status="Success", detail="User changed their password")
    return {"message": "Password updated successfully."}


@app.post("/api/auth/logout", tags=["Auth"])
async def logout_user(
    token: str  = Depends(_oauth2),
    user: dict  = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """Revoke the current JWT and write a logout audit event."""
    _REVOKED_TOKENS.add(token)
    email = user.get("sub", "unknown")
    await _append_audit_db(db, user_uid=email, action_type="Logout",
                           status="Success", detail="User signed out")
    return {"message": "Logged out."}


@app.post("/api/auth/update-profile", tags=["Auth"])
async def update_profile(
    req:  UpdateProfileRequest,
    user: dict = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """Update the display name (and future profile fields) for the authenticated user."""
    email   = user.get("sub", "")
    result  = await db.execute(select(UserModel).where(UserModel.email == email))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(404, "User not found.")
    if req.name is not None and req.name.strip():
        db_user.name = req.name.strip()
    await _append_audit_db(db, user_uid=email, action_type="Profile Updated",
                           status="Success", detail="User updated their profile")
    return {
        "message": "Profile updated successfully.",
        "user": {"email": db_user.email, "name": db_user.name, "role": db_user.role},
    }

# ─────────────────────────────────────────────────────────────────────────────
# Ingest Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/data", tags=["Data"])
async def get_data(user: dict = Depends(get_current_user)):
    """Return up to 1,000 rows from the loaded dataset, filtered by role."""
    if _DATA is None or _DATA.empty:
        return {"columns": [], "rows": [], "total": 0, "filtered": 0}
    df = _role_filter(_DATA.copy(), user)
    return {
        "columns":  list(df.columns),
        "rows":     df.head(1000).fillna("").to_dict("records"),
        "total":    len(df),
        "filtered": min(len(df), 1000),
    }


@app.get("/api/summary", tags=["Data"])
async def get_summary(user: dict = Depends(get_current_user)):
    """Return per-subject row counts and average marks for the current user scope."""
    if _DATA is None or _DATA.empty:
        return {"data": []}
    df = _role_filter(_DATA.copy(), user)
    if "SUBJECTCODE" not in df.columns:
        return {"data": []}
    mark_col = next(
        (c for c in df.columns if "PCT" in c.upper() or "PERCENT" in c.upper()
         or "MARKPERCENT" in c.upper()),
        None,
    )
    grouped = df.groupby("SUBJECTCODE")
    result  = []
    for code, grp in grouped:
        entry: dict = {"subject_code": code, "row_count": len(grp)}
        if mark_col:
            entry["avg_mark"] = round(grp[mark_col].mean(), 1)
        result.append(entry)
    result.sort(key=lambda x: x["subject_code"])
    return {"data": result}


@app.get("/api/filters", tags=["Data"])
async def get_filters(user: dict = Depends(get_current_user)):
    """Return subjects visible to the requesting user and all available study periods."""
    periods: list[str] = []
    if _DATA is not None and "STUDYPERIOD" in _DATA.columns:
        periods = sorted(
            _DATA["STUDYPERIOD"].dropna().unique().tolist(),
            key=lambda x: float(x),
        )
    if user.get("role") == "Lecturer":
        return {"subjects": user.get("subjects", []), "periods": periods}
    if _DATA is not None and "SUBJECTCODE" in _DATA.columns:
        return {"subjects": sorted(_DATA["SUBJECTCODE"].dropna().unique().tolist()), "periods": periods}
    return {"subjects": [], "periods": periods}


# ── Two-phase ingestion: analyze (parse + classify, no commit) then confirm
# (commit) — nothing reaches the live _DATA/_ATTENDANCE until confirm is
# called with the token an analyze call returned. The pending upload
# (raw CSV bytes, not a cached DataFrame) is persisted in Postgres — see
# PendingIngest in app/db/models.py — not an in-memory dict, because prod
# runs 4 gunicorn workers (docker-compose.prod.yml: `--workers 4`), each a
# separate OS process; an in-memory dict would only be visible to whichever
# worker happened to handle analyze, so confirm would 404 whenever a
# non-sticky load balancer routed it to a different worker. One row per
# kind (kind is the primary key) — a new analyze for the same kind
# overwrites the previous pending row, same "old token becomes invalid"
# protection the dict had. Rows older than PENDING_INGEST_TTL_MINUTES are
# treated as expired and rejected at confirm time.
PENDING_INGEST_TTL_MINUTES = 30


async def _save_pending_ingest(db: AsyncSession, kind: str, token: str, filename: Optional[str], content: bytes) -> None:
    await db.execute(delete(PendingIngest).where(PendingIngest.kind == kind))
    db.add(PendingIngest(kind=kind, token=token, filename=filename, csv_bytes=content))
    await db.commit()


async def _load_pending_ingest(db: AsyncSession, kind: str, token: str) -> Optional[PendingIngest]:
    result = await db.execute(select(PendingIngest).where(PendingIngest.kind == kind))
    row = result.scalar_one_or_none()
    if row is None or row.token != token:
        return None
    age_minutes = (datetime.now(timezone.utc) - row.created_at).total_seconds() / 60
    if age_minutes > PENDING_INGEST_TTL_MINUTES:
        return None
    return row


async def _delete_pending_ingest(db: AsyncSession, kind: str) -> None:
    await db.execute(delete(PendingIngest).where(PendingIngest.kind == kind))
    await db.commit()

# ── Ingest-confirm lock ──────────────────────────────────────────────────────
# ingest_capstone_confirm() writes the ingested file to a shared path
# (INGESTED_CAPSTONE_PATH) then temporarily monkey-patches the module-level
# train_model.DATA_PATH / check_new_period.DATA_PATH globals for the
# duration of the retrain check. Within one worker process this is safe —
# the whole critical section is synchronous Python with zero `await`
# points, so asyncio can't interleave another request into it — but in a
# multi-worker prod deployment (gunicorn + several uvicorn workers, per
# this project's Dockerfile.prod) two workers are separate OS processes
# that could genuinely run this section concurrently and race on the
# SAME shared file. Same fix as model_registry.py's already-proven
# .registry.lock: an atomic O_CREAT|O_EXCL file lock, file-based so it's
# shared across worker processes (unlike the in-memory DATA_PATH
# variables themselves), with the same stale-lock recovery and
# wait-then-fail-cleanly behavior.
_INGEST_LOCK_PATH = Path(__file__).parent / "ml" / ".ingest.lock"
_INGEST_LOCK_STALE_SECONDS = 30 * 60
_INGEST_LOCK_WAIT_MAX_SECONDS = 5 * 60
_INGEST_LOCK_POLL_INTERVAL_SECONDS = 1


class IngestLockTimeout(RuntimeError):
    """Raised when the ingest lock couldn't be acquired within _INGEST_LOCK_WAIT_MAX_SECONDS."""


def _acquire_ingest_lock() -> None:
    import os as _os
    import time as _time
    from datetime import datetime as _datetime, timezone as _timezone

    _INGEST_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    deadline = _time.monotonic() + _INGEST_LOCK_WAIT_MAX_SECONDS
    while True:
        try:
            fd = _os.open(_INGEST_LOCK_PATH, _os.O_CREAT | _os.O_EXCL | _os.O_WRONLY)
            with _os.fdopen(fd, "w") as f:
                f.write(f"{_os.getpid()} {_datetime.now(_timezone.utc).isoformat()}\n")
            return
        except FileExistsError:
            pass

        try:
            age = _time.time() - _INGEST_LOCK_PATH.stat().st_mtime
        except FileNotFoundError:
            continue  # released between our open() and stat() — retry immediately

        if age > _INGEST_LOCK_STALE_SECONDS:
            with contextlib.suppress(FileNotFoundError):
                _INGEST_LOCK_PATH.unlink()
            continue

        if _time.monotonic() >= deadline:
            raise IngestLockTimeout(
                f"Could not acquire the ingest lock within {_INGEST_LOCK_WAIT_MAX_SECONDS}s — "
                f"another capstone ingest appears to still be in progress."
            )
        _time.sleep(_INGEST_LOCK_POLL_INTERVAL_SECONDS)


def _release_ingest_lock() -> None:
    with contextlib.suppress(FileNotFoundError):
        _INGEST_LOCK_PATH.unlink()


def _reject_upload_common(content: bytes, max_bytes: int) -> Optional[str]:
    """Shared validation for both capstone and attendance uploads. Returns an error string, or None if OK."""
    if len(content) > max_bytes:
        return f"File exceeds the {max_bytes // (1024*1024)} MB limit."
    if len(content) == 0:
        return "Uploaded file is empty."
    head = content[:2000]
    _BINARY_SIGS = (b"PK", b"%PDF", b"\x89PNG", b"\xff\xd8", b"\x42\x4d")
    if any(head.startswith(sig) for sig in _BINARY_SIGS) or b"," not in head:
        return "File does not appear to be a valid CSV."
    return None


def _capstone_analysis_from_bytes(content: bytes, filename: Optional[str]) -> dict:
    """Parse + classify capstone CSV bytes into the analyze()-shaped payload.

    Shared by the upload-time analyze endpoint and the status endpoint (which
    reclassifies the same bytes already sitting in PendingIngest) so the two
    can never drift into returning different shapes for the same upload.
    """
    from app.ml.column_classification import CAPSTONE_KEEP, classify_columns

    df = pd.read_csv(io.BytesIO(content))
    df.columns = [c.strip() for c in df.columns]

    missing_keep = [c for c in CAPSTONE_KEEP if c not in df.columns]
    if missing_keep:
        raise HTTPException(400, f"Missing required column: {missing_keep[0]}")

    classification = classify_columns(df.columns.tolist(), "capstone")
    periods = (
        sorted(df["STUDYPERIOD"].dropna().apply(lambda x: round(float(x), 1)).unique().tolist())
        if "STUDYPERIOD" in df.columns else []
    )
    return {
        "row_count": len(df),
        "subjects":  int(df["SUBJECTCODE"].nunique()) if "SUBJECTCODE" in df.columns else 0,
        "periods":   periods,
        "columns":   classification,
        "filename":  filename,
    }


def _attendance_analysis_from_bytes(content: bytes, filename: Optional[str]) -> dict:
    """Parse + classify attendance CSV bytes into the analyze()-shaped payload. See
    _capstone_analysis_from_bytes for why this is shared with the status endpoint."""
    from app.ml.column_classification import classify_columns

    df = pd.read_csv(io.BytesIO(content))
    df.columns = [c.strip() for c in df.columns]

    required = ["STUDENTID_MASKED", "course", "study_period_code", "year", "attendance_code"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise HTTPException(400, f"Missing required column: {missing[0]}")

    classification = classify_columns(df.columns.tolist(), "attendance")
    return {
        "row_count": len(df),
        "columns":   classification,
        "filename":  filename,
    }


@app.get("/api/ingest/{kind}/status", tags=["Ingest"])
async def ingest_status(
    kind: str,
    user: dict = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """
    Report whether an already-analyzed-but-not-yet-confirmed upload is still
    sitting server-side for this kind (see PendingIngest / PENDING_INGEST_TTL_MINUTES
    above), so the frontend can resume review/confirm after a page refresh
    instead of asking the user to re-pick and re-upload a file that can be
    up to 200MB just to get back to where they were.
    """
    if kind not in ("capstone", "attendance"):
        raise HTTPException(400, "kind must be 'capstone' or 'attendance'")

    result = await db.execute(select(PendingIngest).where(PendingIngest.kind == kind))
    row = result.scalar_one_or_none()
    if row is None:
        return {"pending": False}

    age_seconds = (datetime.now(timezone.utc) - row.created_at).total_seconds()
    if age_seconds > PENDING_INGEST_TTL_MINUTES * 60:
        return {"pending": False}

    try:
        analysis = (
            _capstone_analysis_from_bytes(row.csv_bytes, row.filename) if kind == "capstone"
            else _attendance_analysis_from_bytes(row.csv_bytes, row.filename)
        )
    except HTTPException:
        # Stored bytes no longer classify cleanly (e.g. a column decision
        # changed since analyze) — treat as nothing-to-resume rather than
        # surfacing a confusing error on page load.
        return {"pending": False}

    return {
        "pending":            True,
        "token":              row.token,
        "expires_in_seconds": int(PENDING_INGEST_TTL_MINUTES * 60 - age_seconds),
        **analysis,
    }


async def _run_analyze_job(
    job_id: int, content: bytes, filename: Optional[str], user_email: str, kind: str,
) -> None:
    """
    Background body of analyze — parses + classifies the already-received
    upload and stashes the result as a PendingIngest, exactly what the old
    synchronous analyze endpoint did inline. Split out so a client
    disconnect (page refresh, closed tab) while this runs can't silently
    lose the analysis: once the browser has finished sending the file,
    everything after that point is durable and runs independently of the
    request/response cycle — the same fix already applied to confirm.

    Needs its own AsyncSession, same reasoning as _run_capstone_confirm_job:
    the request-scoped session is closed by the time BackgroundTasks runs.
    """
    async with _AsyncSession() as db:
        job = await db.get(AnalyzeJob, job_id)

        try:
            analysis = (
                _capstone_analysis_from_bytes(content, filename) if kind == "capstone"
                else _attendance_analysis_from_bytes(content, filename)
            )
        except HTTPException as exc:
            status_label = "Error" if exc.status_code == 422 else "Alert"
            job.status = "failed"
            job.error_detail = str(exc.detail)
            job.finished_at = datetime.now(timezone.utc)
            await _append_audit_db(db, user_uid=user_email, action_type="Data Upload",
                                   status=status_label, detail=f"Rejected {kind} upload: {exc.detail}")
            await db.commit()
            return
        except Exception as exc:
            job.status = "failed"
            job.error_detail = "The uploaded file could not be parsed as a valid CSV."
            job.finished_at = datetime.now(timezone.utc)
            await _append_audit_db(db, user_uid=user_email, action_type="Data Upload",
                                   status="Error", detail=f"Failed to parse {kind} CSV: {exc}")
            await db.commit()
            return

        token = str(uuid.uuid4())
        await _save_pending_ingest(db, kind, token, filename, content)
        job.status = "success"
        job.result = {"token": token, **analysis}
        job.finished_at = datetime.now(timezone.utc)
        await db.commit()


@app.get("/api/ingest/{kind}/analyze-status", tags=["Ingest"])
async def ingest_analyze_status(
    kind: str,
    user: dict = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """
    Whether an analyze from before a page refresh is still running (or most
    recently failed) for this kind, so the page can resume showing
    "Analyzing…" (or the failure) instead of looking blank while that
    background job keeps working. A *successful* analyze doesn't need
    anything here — its result already lives in PendingIngest, covered by
    GET /api/ingest/{kind}/status.
    """
    if kind not in ("capstone", "attendance"):
        raise HTTPException(400, "kind must be 'capstone' or 'attendance'")

    result = await db.execute(
        select(AnalyzeJob).where(AnalyzeJob.kind == kind).order_by(AnalyzeJob.id.desc()).limit(1)
    )
    job = result.scalar_one_or_none()
    if job is None or job.status == "success":
        return {"active": False}

    # A failed analyze only matters for a little while — don't resurrect an
    # old failure indefinitely on every page load.
    age_minutes = (datetime.now(timezone.utc) - job.started_at).total_seconds() / 60
    if job.status == "failed" and age_minutes > PENDING_INGEST_TTL_MINUTES:
        return {"active": False}

    return {
        "active":       True,
        "job_id":       job.id,
        "status":       job.status,
        "filename":     job.filename,
        "error_detail": job.error_detail,
    }


@app.get("/api/ingest/analyze-jobs", tags=["Ingest"])
async def analyze_jobs_list(
    limit: int = Query(30, ge=1, le=200),
    user: dict = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """Recent analyze jobs (both kinds), most recent first — merged with
    GET /api/ingest/jobs client-side into one Ingestion Activity timeline."""
    result = await db.execute(select(AnalyzeJob).order_by(AnalyzeJob.id.desc()).limit(limit))
    jobs = result.scalars().all()
    return {
        "jobs": [
            {
                "id":           j.id,
                "kind":         j.kind,
                "status":       j.status,
                "filename":     j.filename,
                "started_by":   j.started_by,
                "started_at":   j.started_at.isoformat() if j.started_at else None,
                "finished_at":  j.finished_at.isoformat() if j.finished_at else None,
                "result":       j.result,
                "error_detail": j.error_detail,
            }
            for j in jobs
        ]
    }


@app.get("/api/ingest/analyze-jobs/{job_id}", tags=["Ingest"])
async def analyze_job_detail(
    job_id: int,
    user: dict = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """Poll a single analyze job — used right after upload to watch that
    specific run without waiting for the next full jobs-list refresh."""
    job = await db.get(AnalyzeJob, job_id)
    if job is None:
        raise HTTPException(404, "No analyze job with that id.")
    return {
        "id":           job.id,
        "kind":         job.kind,
        "status":       job.status,
        "filename":     job.filename,
        "started_by":   job.started_by,
        "started_at":   job.started_at.isoformat() if job.started_at else None,
        "finished_at":  job.finished_at.isoformat() if job.finished_at else None,
        "result":       job.result,
        "error_detail": job.error_detail,
    }


@app.post("/api/ingest/capstone/analyze", status_code=202, tags=["Ingest"])
async def ingest_capstone_analyze(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: dict = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """
    Accept a capstone CSV upload and return immediately — the actual parse +
    column classification (and the PendingIngest write it produces) happens
    in the background so a page refresh while this runs doesn't lose it.
    Poll GET /api/ingest/analyze-jobs/{job_id} (or GET
    /api/ingest/{kind}/analyze-status after a refresh) to see when it
    finishes; the result is the same {token, row_count, columns, ...}
    payload this endpoint used to return directly.
    """
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext != "csv":
        raise HTTPException(400, "Unsupported file type. Only .csv files are accepted.")

    content = await file.read()
    err = _reject_upload_common(content, MAX_UPLOAD_BYTES)
    if err:
        await _append_audit_db(db, user_uid=user["sub"], action_type="Data Upload",
                               status="Alert", detail=f"Rejected capstone upload: {err}")
        raise HTTPException(400, err)

    job = AnalyzeJob(kind="capstone", filename=file.filename, started_by=user["sub"])
    db.add(job)
    await db.commit()
    await db.refresh(job)

    background_tasks.add_task(_run_analyze_job, job.id, content, file.filename, user["sub"], "capstone")
    return {"job_id": job.id, "status": "running"}


async def _run_capstone_confirm_job(
    job_id: int, csv_bytes: bytes, filename: Optional[str], user_email: str, mode: str,
) -> None:
    """
    Background body of capstone confirm — runs after the HTTP response is
    already sent (see ingest_capstone_confirm below). Opens its own DB
    session: the request's session is closed by the time this runs, and in
    a multi-worker deployment this task and a later GET /api/ingest/jobs
    poll may not even be the same process.

    Runs the SAME collapse_attempts_to_latest_per_type() logic training
    uses — no attempt-1-only path anywhere in this flow. Writes the file to
    DATA_PATH on disk (required for check_new_period.py / train_model.py,
    both disk-based, to see the new data) and checks for a genuinely new
    study period, registering a retrain candidate if so — never
    auto-promoting.

    mode is "override" (replace the live dataset wholesale — the original,
    only behavior) or "incremental" (merge new rows into the current _DATA
    via app.ml.incremental_merge — see _do_capstone_confirm).
    """
    global _DATA, _ATTENDANCE

    async with _AsyncSession() as db:
        job = await db.get(IngestJob, job_id)

        try:
            pending_df = pd.read_csv(io.BytesIO(csv_bytes))
            result = await _do_capstone_confirm(pending_df, mode)
        except Exception as exc:
            job.status = "failed"
            job.error_detail = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            await _append_audit_db(
                db, user_uid=user_email, action_type="Data Upload", status="Error",
                detail=f"Capstone ingestion failed for {filename}: {exc}",
            )
            await db.commit()
            return

        job.status = "success"
        job.result = result
        job.finished_at = datetime.now(timezone.utc)
        merge_detail = ""
        if result.get("merge_stats"):
            ms = result["merge_stats"]
            merge_detail = (
                f", incremental merge — {ms['new_rows']:,} new, {ms['updated_rows']:,} updated, "
                f"{ms['redundant_rows']:,} redundant/skipped"
            )
        await _append_audit_db(
            db, user_uid=user_email, action_type="Data Upload", status="Success",
            detail=f"{result['row_count']:,} rows ingested from {filename} "
                   f"(subjects reclassified: {result['subjects_reclassified']}, "
                   f"retrain triggered: {result['retrain']['triggered']}{merge_detail})",
        )
        await db.commit()


CAPSTONE_MERGE_KEY_COLS = ["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD", "ASSESSMENTTYPECODE", "ATTEMPTNUMBER"]


async def _do_capstone_confirm(pending_df: pd.DataFrame, mode: str = "override") -> dict:
    """The actual parse/feature/retrain-check/commit work, shared by nothing
    else — split out of _run_capstone_confirm_job purely so that function's
    try/except stays about job bookkeeping, not this logic.

    mode="incremental" merges pending_df's rows into the current _DATA (see
    CAPSTONE_MERGE_KEY_COLS / app.ml.incremental_merge) instead of replacing
    it outright — an exact-duplicate row (by that key) is skipped, a
    same-key row with any different value is treated as a correction and
    replaces the old one, and a new key is appended. Falls back to the plain
    override behavior if there's no existing data to merge into yet.
    """
    global _DATA, _ATTENDANCE

    df = pending_df.copy()
    if "STUDYPERIOD" in df.columns:
        df["STUDYPERIOD"] = df["STUDYPERIOD"].apply(
            lambda x: str(round(float(x), 1)) if pd.notna(x) else ""
        )
    if "MARKPERCENT" in df.columns:
        df["MARKPERCENT"] = pd.to_numeric(df["MARKPERCENT"], errors="coerce")
    # Computed here (before any merge) rather than at its original spot
    # further down, so it's a column on BOTH sides of the incremental merge
    # below — _DATA (from a prior confirm) already carries it, and without
    # this it would be silently dropped from merged_df (merge_incremental
    # only keeps columns present in both dataframes).
    df["PASSED"] = df["MARKPERCENT"] >= 50

    merge_stats = None
    if mode == "incremental" and _DATA is not None and not _DATA.empty:
        from app.ml.incremental_merge import merge_incremental
        df, merge_stats = merge_incremental(_DATA, df, key_cols=CAPSTONE_MERGE_KEY_COLS)

    from app.ml.train_model import collapse_attempts_to_latest_per_type, build_target, RELIABILITY_PATH

    collapsed = collapse_attempts_to_latest_per_type(df.dropna(subset=["MARKPERCENT"]))

    # Subjects reclassified — same per-enrolment weighting-sum check
    # identify_clean_subjects.py uses (automated part only, no manual
    # overrides — those are documented, subject-specific exceptions that
    # don't generalize to an arbitrary new upload), diffed against the
    # currently-loaded subject_reliability.json. Reported, not auto-applied
    # — matches this project's "show the diff before overwriting" pattern.
    subjects_reclassified = 0
    try:
        w = collapsed.groupby(["SUBJECTCODE", "STUDYPERIOD", "STUDENTID_MASKED"])["WEIGHTING"].sum()
        clean = w.between(99.0, 101.0)
        stats = clean.groupby(level="SUBJECTCODE").mean() * 100
        def _cat(pct):
            if pct == 100.0:
                return "FULLY_CLEAN"
            if pct >= 90.0:
                return "MOSTLY_CLEAN"
            return "UNRELIABLE"
        new_cats = {s: _cat(p) for s, p in stats.items()}
        with open(RELIABILITY_PATH) as f:
            old_rel = json.load(f)
        old_cats = {}
        for s in old_rel.get("fully_clean", []):
            old_cats[s] = "FULLY_CLEAN"
        for s in old_rel.get("mostly_clean", []):
            old_cats[s] = "MOSTLY_CLEAN"
        for s in old_rel.get("unreliable", []):
            old_cats[s] = "UNRELIABLE"
        subjects_reclassified = sum(
            1 for s in new_cats if s in old_cats and old_cats[s] != new_cats[s]
        )
    except Exception:
        subjects_reclassified = 0

    # Write to disk — required for check_new_period.py / train_model.py
    # (both read DATA_PATH from disk), and so the newly ingested data
    # survives a container restart rather than being an ephemeral
    # in-memory-only override.
    # data/ is mounted READ-ONLY in the backend container (./data:/data:ro
    # in docker-compose.yml — the same deliberate protection that already
    # applies to build_attendance_features.py's output). Writing the
    # ingested file to DATA_PATH directly fails with EROFS. Instead: write
    # to a writable location (the backend bind mount in dev, or the shared
    # `ingested_data_prod` volume in prod — see train_model.INGESTED_DATA_DIR's
    # docstring for why this is env-var-driven rather than hardcoded to this
    # file's own directory), then temporarily point train_model.DATA_PATH /
    # check_new_period.DATA_PATH (and train_model.ATTENDANCE_PATH, if
    # attendance has ever been ingested) at it — the same monkey-patch
    # pattern verify_dynamic_period_e2e.py already uses for isolated retrain
    # testing — restoring all of them afterward regardless of outcome. This
    # is required for check_new_period.py and train_model.py to actually
    # see the newly ingested data (all read their paths from disk, not from
    # the in-memory _DATA/_ATTENDANCE this endpoint also updates).
    import app.ml.train_model as train_model_mod
    train_model_mod.INGESTED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    INGESTED_CAPSTONE_PATH = train_model_mod.INGESTED_DATA_DIR / "ingested_capstone.csv"
    # Written by _do_attendance_confirm (same raw per-session shape
    # load_attendance_raw() expects from ATTENDANCE_PATH) — if an admin has
    # ever ingested attendance through the UI, retraining should train on
    # that instead of silently falling back to the archived /data file.
    INGESTED_ATTENDANCE_RAW_PATH = train_model_mod.INGESTED_DATA_DIR / "ingested_attendance_raw.csv"

    # Refresh the PASS target merged into _ATTENDANCE, if attendance data
    # is already loaded, so it stays consistent with the new capstone data.
    new_attendance = _ATTENDANCE
    if _ATTENDANCE is not None and not _ATTENDANCE.empty and "PASS" in _ATTENDANCE.columns:
        try:
            new_target = build_target(collapsed)
            att_no_pass = _ATTENDANCE.drop(columns=["PASS"])
            new_attendance = att_no_pass.merge(
                new_target, on=["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"], how="left"
            )
        except Exception:
            pass

    # Retrain trigger — candidate registration only, never auto-promote.
    # Lock-protected (see _acquire_ingest_lock's docstring above): the disk
    # write and the DATA_PATH monkey-patch both touch state shared across
    # worker processes in a multi-worker deployment, so only one confirm can
    # be in this section at a time, process-wide.
    import app.ml.check_new_period as check_new_period_mod
    from app.ml.model_registry import load_registry

    _acquire_ingest_lock()
    try:
        if merge_stats is not None:
            # An incremental merge: the on-disk file (what check_new_period.py
            # / train_model.py actually read for retraining) must reflect the
            # FULL merged dataset, not just this upload's new rows — written
            # back in the same raw shape pending_df originally had (no
            # derived PASSED column, STUDYPERIOD as a plain float) so it
            # round-trips identically to a normal override's raw upload.
            disk_df = df.drop(columns=["PASSED"])
            # coerce, not astype — a blank STUDYPERIOD normalizes to "" above
            # (pd.notna(x) is False), and .astype(float) would raise on that
            # rather than round-trip it back to NaN like the source CSV had.
            disk_df["STUDYPERIOD"] = pd.to_numeric(disk_df["STUDYPERIOD"], errors="coerce")
            disk_df.to_csv(INGESTED_CAPSTONE_PATH, index=False)
        else:
            pending_df.to_csv(INGESTED_CAPSTONE_PATH, index=False)
        _DATA = df
        _ATTENDANCE = new_attendance

        original_paths = {
            "train_model":            train_model_mod.DATA_PATH,
            "check_new_period":       check_new_period_mod.DATA_PATH,
            "train_model_attendance": train_model_mod.ATTENDANCE_PATH,
        }
        retrain_info = {"triggered": False, "reason": None, "candidate_version": None}
        try:
            train_model_mod.DATA_PATH = INGESTED_CAPSTONE_PATH
            check_new_period_mod.DATA_PATH = INGESTED_CAPSTONE_PATH
            if INGESTED_ATTENDANCE_RAW_PATH.exists():
                train_model_mod.ATTENDANCE_PATH = INGESTED_ATTENDANCE_RAW_PATH

            is_new, latest, validated_on = check_new_period_mod.new_period_available()
            if is_new:
                before_versions = {v["version"] for v in load_registry().get("versions", [])}
                train_model_mod.main()
                after_versions = {v["version"] for v in load_registry().get("versions", [])}
                new_versions = after_versions - before_versions
                retrain_info = {
                    "triggered": True,
                    "reason": f"New period detected: {latest} (live model validated on {validated_on})",
                    "candidate_version": sorted(new_versions)[-1] if new_versions else None,
                }
            else:
                retrain_info["reason"] = f"No new period (latest in data: {latest}, live validated on: {validated_on})"
        except Exception as exc:
            retrain_info["reason"] = f"Retrain check failed: {exc}"
        finally:
            train_model_mod.DATA_PATH = original_paths["train_model"]
            check_new_period_mod.DATA_PATH = original_paths["check_new_period"]
            train_model_mod.ATTENDANCE_PATH = original_paths["train_model_attendance"]
    finally:
        _release_ingest_lock()

    return {
        "row_count":              len(df),
        "columns":                list(df.columns),
        "subjects_reclassified":  subjects_reclassified,
        "retrain":                retrain_info,
        "promotion_note":         "Model promotion stays manual",
        "merge_stats":            merge_stats,
        "message":                f"{len(df):,} rows successfully loaded",
    }


@app.post("/api/ingest/capstone/confirm", status_code=202, tags=["Ingest"])
async def ingest_capstone_confirm(
    payload: dict,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """
    Accept a previously-analyzed capstone upload (by token) for ingestion and
    return immediately — the actual parse/retrain-check/commit work (which
    can run past any reasonable request timeout on a large file, see
    build_attendance_features's confirm counterpart) happens in the
    background. Poll GET /api/ingest/jobs/{job_id} (or GET /api/ingest/jobs
    for the full recent list) to see when it finishes.

    payload.mode: "override" (default — replace the live dataset wholesale)
    or "incremental" (merge into the current data; see _do_capstone_confirm
    / app.ml.incremental_merge). The frontend only offers a real choice
    when GET /api/ingest/dataset-summary reports existing data for this
    kind — with nothing to merge into, "incremental" and "override" behave
    identically anyway.
    """
    mode = payload.get("mode", "override")
    if mode not in ("override", "incremental"):
        raise HTTPException(400, "mode must be 'override' or 'incremental'")

    token = payload.get("token")
    pending_row = await _load_pending_ingest(db, "capstone", token)
    if pending_row is None:
        raise HTTPException(404, "No matching pending capstone upload (or it expired). Analyze the file again.")

    # Delete the pending row now, not after the background job finishes —
    # this token is spent the moment ingestion is accepted, same as the old
    # synchronous confirm, so a duplicate click can't resubmit it.
    csv_bytes, filename = pending_row.csv_bytes, pending_row.filename
    await _delete_pending_ingest(db, "capstone")

    job = IngestJob(kind="capstone", filename=filename, mode=mode, started_by=user["sub"])
    db.add(job)
    await db.commit()
    await db.refresh(job)

    background_tasks.add_task(_run_capstone_confirm_job, job.id, csv_bytes, filename, user["sub"], mode)
    return {
        "job_id":  job.id,
        "status":  "running",
        "message": "Capstone ingestion started in the background — you'll be notified here once it finishes.",
    }


@app.get("/api/ingest/preview", tags=["Ingest"])
async def ingest_preview(
    page:      int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    user: dict = Depends(require_head_of_school),
):
    """Return a paginated slice of the currently loaded dataset."""
    if _DATA is None or _DATA.empty:
        return {
            "total": 0, "page": page, "page_size": page_size,
            "total_pages": 0, "columns": [], "data": [],
        }
    total       = len(_DATA)
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    start       = (page - 1) * page_size
    page_df     = _DATA.iloc[start: start + page_size]
    return {
        "total":       total,
        "page":        page,
        "page_size":   page_size,
        "total_pages": total_pages,
        "columns":     list(_DATA.columns),
        "data":        page_df.fillna("").to_dict("records"),
    }


@app.post("/api/ingest/attendance/analyze", status_code=202, tags=["Ingest"])
async def ingest_attendance_analyze(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: dict = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """
    Accept an attendance CSV upload and return immediately — see
    ingest_capstone_analyze's docstring for the full reasoning (same
    BackgroundTasks fix, applied here too). A separate, clearly distinct
    slot from the capstone analyze endpoint — the two file types are never
    accepted through the same endpoint, so they can't be cross-uploaded
    into the wrong slot.
    """
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext != "csv":
        raise HTTPException(400, "Unsupported file type. Only .csv files are accepted.")

    content = await file.read()
    err = _reject_upload_common(content, MAX_ATTENDANCE_UPLOAD_BYTES)
    if err:
        await _append_audit_db(db, user_uid=user["sub"], action_type="Data Upload",
                               status="Alert", detail=f"Rejected attendance upload: {err}")
        raise HTTPException(400, err)

    job = AnalyzeJob(kind="attendance", filename=file.filename, started_by=user["sub"])
    db.add(job)
    await db.commit()
    await db.refresh(job)

    background_tasks.add_task(_run_analyze_job, job.id, content, file.filename, user["sub"], "attendance")
    return {"job_id": job.id, "status": "running"}


ATTENDANCE_MERGE_KEY_COLS = ["STUDENTID_MASKED", "course", "study_period_code", "cls_session_no"]


async def _run_attendance_confirm_job(
    job_id: int, csv_bytes: bytes, filename: Optional[str], user_email: str, mode: str,
) -> None:
    """Background body of attendance confirm — see _run_capstone_confirm_job's
    docstring for why this needs its own session and can't reuse the request's.

    mode is "override" (replace the persisted raw attendance dataset
    wholesale) or "incremental" (merge new session rows into it — see
    ATTENDANCE_MERGE_KEY_COLS / _do_attendance_confirm)."""
    global _ATTENDANCE

    async with _AsyncSession() as db:
        job = await db.get(IngestJob, job_id)

        try:
            result = await _do_attendance_confirm(csv_bytes, mode)
        except Exception as exc:
            job.status = "failed"
            job.error_detail = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            await _append_audit_db(
                db, user_uid=user_email, action_type="Data Upload", status="Error",
                detail=f"Attendance ingestion failed for {filename}: {exc}",
            )
            await db.commit()
            return

        job.status = "success"
        job.result = result
        job.finished_at = datetime.now(timezone.utc)
        merge_detail = ""
        if result.get("merge_stats"):
            ms = result["merge_stats"]
            merge_detail = (
                f", incremental merge — {ms['new_rows']:,} new, {ms['updated_rows']:,} updated, "
                f"{ms['redundant_rows']:,} redundant/skipped"
            )
        await _append_audit_db(
            db, user_uid=user_email, action_type="Data Upload", status="Success",
            detail=f"{result['row_count']:,} attendance enrolments ingested from {filename} "
                   f"(match rate vs current capstone data: {result['match_rate']}%{merge_detail})",
        )
        await db.commit()


async def _do_attendance_confirm(csv_bytes: bytes, mode: str = "override") -> dict:
    """The actual feature-build/merge work, split out of _run_attendance_confirm_job
    purely so that function's try/except stays about job bookkeeping, not this logic.

    Persists the raw (pre-aggregation, per-class-session) attendance rows at
    INGESTED_ATTENDANCE_RAW_PATH on every successful confirm, in BOTH modes
    — that's what the NEXT incremental confirm merges new rows into (see
    ATTENDANCE_MERGE_KEY_COLS). build_attendance_features() always
    aggregates from that persisted file rather than straight from the raw
    upload, so an override's result is identical to before either way, but
    an incremental's reflects the full accumulated session history across
    every upload, not just this one file.
    """
    global _ATTENDANCE

    import app.ml.train_model as train_model_mod
    from app.ml.build_attendance_features import build_attendance_features

    train_model_mod.INGESTED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    ingested_attendance_raw_path = train_model_mod.INGESTED_DATA_DIR / "ingested_attendance_raw.csv"

    new_raw_df = pd.read_csv(io.BytesIO(csv_bytes))

    merge_stats = None
    if mode == "incremental" and ingested_attendance_raw_path.exists():
        from app.ml.incremental_merge import merge_incremental
        existing_raw_df = pd.read_csv(ingested_attendance_raw_path)
        merged_raw_df, merge_stats = merge_incremental(
            existing_raw_df, new_raw_df, key_cols=ATTENDANCE_MERGE_KEY_COLS,
        )
    else:
        merged_raw_df = new_raw_df

    merged_raw_df.to_csv(ingested_attendance_raw_path, index=False)

    from app.ml.train_model import collapse_attempts_to_latest_per_type, build_target

    capstone_path = _current_capstone_path()
    if not capstone_path.exists():
        # build_attendance_features scopes attendance rows to the capstone
        # data's own subjects/years (see its docstring) — with no capstone
        # data ingested yet (and no bundled sample file present either),
        # there's nothing to scope against. Surfacing this plainly beats
        # letting a raw FileNotFoundError naming an internal filename
        # reach the Ingestion Activity panel.
        raise ValueError(
            "No capstone data has been ingested yet. Ingest capstone data first — "
            "attendance is scoped to the subjects and years found there."
        )
    att_features = build_attendance_features(
        attendance_path=ingested_attendance_raw_path, capstone_path=capstone_path,
    )

    if not _DATA.empty:
        collapsed = collapse_attempts_to_latest_per_type(_DATA.copy())
        target    = build_target(collapsed)
        att_features = att_features.merge(
            target, on=["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"], how="left"
        )

    enrolments = pd.DataFrame()
    if not _DATA.empty:
        collapsed_pop = collapse_attempts_to_latest_per_type(_DATA.copy())
        enrolments = collapsed_pop[["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"]].drop_duplicates()
    match_rate = None
    if not enrolments.empty:
        merged_check = enrolments.merge(
            att_features[["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"]].drop_duplicates(),
            on=["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"], how="left", indicator=True,
        )
        match_rate = round(float((merged_check["_merge"] == "both").mean() * 100), 2)

    _ATTENDANCE = att_features
    return {
        "row_count":   len(att_features),
        "columns":     list(att_features.columns),
        "match_rate":  match_rate,
        "merge_stats": merge_stats,
        "message":     f"{len(att_features):,} attendance enrolments loaded, {match_rate}% match rate against current capstone data",
    }


@app.post("/api/ingest/attendance/confirm", status_code=202, tags=["Ingest"])
async def ingest_attendance_confirm(
    payload: dict,
    background_tasks: BackgroundTasks,
    user: dict = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """
    Accept a previously-analyzed attendance upload (by token) for ingestion
    and return immediately — build_attendance_features() over a 200MB /
    2.5M-row file is real, non-trivial work that has no business blocking
    the request. Poll GET /api/ingest/jobs/{job_id} (or GET /api/ingest/jobs)
    to see when it finishes.

    payload.mode: "override" (default) or "incremental" — see
    _do_attendance_confirm's docstring. Same contract as the capstone
    confirm endpoint above.
    """
    mode = payload.get("mode", "override")
    if mode not in ("override", "incremental"):
        raise HTTPException(400, "mode must be 'override' or 'incremental'")

    token = payload.get("token")
    pending_row = await _load_pending_ingest(db, "attendance", token)
    if pending_row is None:
        raise HTTPException(404, "No matching pending attendance upload (or it expired). Analyze the file again.")

    csv_bytes, filename = pending_row.csv_bytes, pending_row.filename
    await _delete_pending_ingest(db, "attendance")

    job = IngestJob(kind="attendance", filename=filename, mode=mode, started_by=user["sub"])
    db.add(job)
    await db.commit()
    await db.refresh(job)

    background_tasks.add_task(_run_attendance_confirm_job, job.id, csv_bytes, filename, user["sub"], mode)
    return {
        "job_id":  job.id,
        "status":  "running",
        "message": "Attendance ingestion started in the background — you'll be notified here once it finishes.",
    }


@app.get("/api/ingest/jobs", tags=["Ingest"])
async def ingest_jobs(
    limit: int = Query(30, ge=1, le=200),
    user: dict = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """
    Recent ingestion jobs (both kinds), most recent first — backs the
    frontend's notification badge (unseen finished jobs) and the ingestion
    history view. Not scoped to the requesting user: ingestion affects the
    one shared dataset, so every Head of School/Technology should see the
    same in-flight and completed jobs regardless of who triggered them.
    """
    result = await db.execute(select(IngestJob).order_by(IngestJob.id.desc()).limit(limit))
    jobs = result.scalars().all()
    return {
        "jobs": [
            {
                "id":           j.id,
                "kind":         j.kind,
                "status":       j.status,
                "filename":     j.filename,
                "started_by":   j.started_by,
                "started_at":   j.started_at.isoformat() if j.started_at else None,
                "finished_at":  j.finished_at.isoformat() if j.finished_at else None,
                "result":       j.result,
                "error_detail": j.error_detail,
            }
            for j in jobs
        ]
    }


@app.get("/api/ingest/jobs/{job_id}", tags=["Ingest"])
async def ingest_job_detail(
    job_id: int,
    user: dict = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """Poll a single ingestion job — used right after confirm to watch that
    specific run without waiting for the next full jobs-list refresh."""
    job = await db.get(IngestJob, job_id)
    if job is None:
        raise HTTPException(404, "No ingestion job with that id.")
    return {
        "id":           job.id,
        "kind":         job.kind,
        "status":       job.status,
        "filename":     job.filename,
        "started_by":   job.started_by,
        "started_at":   job.started_at.isoformat() if job.started_at else None,
        "finished_at":  job.finished_at.isoformat() if job.finished_at else None,
        "result":       job.result,
        "error_detail": job.error_detail,
    }


@app.get("/api/ingest/dataset-summary", tags=["Ingest"])
async def ingest_dataset_summary(
    user: dict = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """
    Persistent, server-derived status per dataset kind (capstone,
    attendance) — so the Data Ingestion page can show "Ingested — 327,501
    rows, updated 2 days ago" (or "Not yet ingested") on every page load,
    instead of looking blank until the admin triggers something new in this
    browser tab. Also what the frontend checks before offering the
    incremental-vs-override wizard: that choice only makes sense once
    there's existing data to merge into or replace.

    filename/mode/uploaded_by/uploaded_at describe the last SUCCESSFUL,
    NOT-SINCE-CLEARED confirm specifically (not just the most recent
    attempt, which last_job_id/last_status/last_ingested_at below still
    track) — a failed retry after a successful ingest must not overwrite
    what's shown as the currently active dataset's source, and a job whose
    data has since been cleared via DELETE /api/ingest/datasets/{kind}
    (see IngestJob.cleared_at) must stop being reported as active at all,
    consistent with has_data having flipped to false.
    """
    summary = {}
    for kind, df in (("capstone", _DATA), ("attendance", _ATTENDANCE)):
        result = await db.execute(
            select(IngestJob).where(IngestJob.kind == kind).order_by(IngestJob.id.desc()).limit(1)
        )
        last_job = result.scalar_one_or_none()

        result_success = await db.execute(
            select(IngestJob)
            .where(IngestJob.kind == kind, IngestJob.status == "success", IngestJob.cleared_at.is_(None))
            .order_by(IngestJob.id.desc()).limit(1)
        )
        active_job = result_success.scalar_one_or_none()

        summary[kind] = {
            "has_data":  bool(df is not None and not df.empty),
            "row_count": int(len(df)) if df is not None else 0,
            "last_job_id":      last_job.id if last_job else None,
            "last_status":      last_job.status if last_job else None,
            "last_ingested_at": (
                last_job.finished_at.isoformat()
                if last_job and last_job.finished_at else None
            ),
            "filename":    active_job.filename if active_job else None,
            "mode":        active_job.mode if active_job else None,
            "uploaded_by": active_job.started_by if active_job else None,
            "uploaded_at": (
                active_job.finished_at.isoformat()
                if active_job and active_job.finished_at else None
            ),
        }
    return summary


@app.delete("/api/ingest/datasets/{kind}", tags=["Ingest"])
async def delete_ingested_dataset(
    kind: str,
    user: dict         = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """
    Clears the ingested override for one kind (capstone/attendance) and
    reloads the live in-memory dataset from whatever's left — the bundled
    sample file, or nothing at all if that isn't present either (see
    _current_capstone_path/_current_attendance_path). Admin-only: this is
    the one action that can make prediction/dashboard data disappear
    outright, so it's deliberately not something a lecturer — or an
    accidental click — can trigger.

    Clearing capstone also refreshes _ATTENDANCE's merged PASS target
    (same reasoning _do_capstone_confirm already applies when NEW capstone
    data lands — a cleared capstone dataset must not leave attendance
    scored against a target that no longer reflects what's live).

    Does not delete IngestJob history — the row that ingested this data
    stays, for the audit trail — but its cleared_at gets stamped so
    ingest_dataset_summary's "currently active" lookup stops pointing at
    it (see that endpoint's docstring), instead of the job row remaining
    reachable via a status='success' filter alone and reporting stale
    filename/mode next to has_data: false.
    """
    global _DATA, _ATTENDANCE

    if kind not in ("capstone", "attendance"):
        raise HTTPException(404, "kind must be 'capstone' or 'attendance'")

    active_job_result = await db.execute(
        select(IngestJob)
        .where(IngestJob.kind == kind, IngestJob.status == "success", IngestJob.cleared_at.is_(None))
        .order_by(IngestJob.id.desc()).limit(1)
    )
    active_job = active_job_result.scalar_one_or_none()
    if active_job is not None:
        active_job.cleared_at = datetime.now(timezone.utc)

    import app.ml.train_model as train_model_mod
    train_model_mod.INGESTED_DATA_DIR.mkdir(parents=True, exist_ok=True)

    if kind == "capstone":
        (train_model_mod.INGESTED_DATA_DIR / "ingested_capstone.csv").unlink(missing_ok=True)
        try:
            _DATA = _load_capstone_dataframe(_current_capstone_path())
        except Exception:
            _DATA = pd.DataFrame()
        # build_attendance_features scopes attendance rows to the capstone
        # data's own subjects/years — if there's now no capstone data to
        # scope against either (no bundled sample present), attendance
        # can't be correctly rebuilt, and must not be left showing its
        # STALE pre-clear features as if they were still valid (the same
        # failure mode startup already handles by falling back to empty).
        try:
            _ATTENDANCE = _load_attendance_dataframe()
        except Exception:
            _ATTENDANCE = pd.DataFrame()
    else:
        (train_model_mod.INGESTED_DATA_DIR / "ingested_attendance_raw.csv").unlink(missing_ok=True)
        try:
            _ATTENDANCE = _load_attendance_dataframe()
        except Exception:
            _ATTENDANCE = pd.DataFrame()

    await _append_audit_db(
        db, user_uid=user["sub"], action_type="Data Upload", status="Success",
        detail=f"Cleared the ingested {kind} dataset",
    )
    await db.commit()

    current_df = _DATA if kind == "capstone" else _ATTENDANCE
    return {"kind": kind, "cleared": True, "has_data": bool(current_df is not None and not current_df.empty)}


@app.post("/api/ingest/columns/decide", tags=["Ingest"])
async def ingest_columns_decide(
    payload: dict,
    user: dict = Depends(require_head_of_school),
):
    """
    Persist a reviewer's keep/permanently_skip decision for a NEW column,
    so it's classified consistently (no longer flagged as NEW) on every
    future upload — payload: {"kind": "capstone"|"attendance", "column": str, "decision": "keep"|"permanently_skip"}.
    """
    from app.ml.column_classification import record_column_decision

    kind     = payload.get("kind")
    column   = payload.get("column")
    decision = payload.get("decision")
    if kind not in ("capstone", "attendance"):
        raise HTTPException(400, "kind must be 'capstone' or 'attendance'")
    if decision not in ("keep", "permanently_skip"):
        raise HTTPException(400, "decision must be 'keep' or 'permanently_skip'")
    if not column:
        raise HTTPException(400, "column is required")

    record_column_decision(kind, column, decision)
    return {"message": f"Column '{column}' ({kind}) recorded as '{decision}'."}


@app.get("/api/ingest/attendance/preview", tags=["Ingest"])
async def ingest_attendance_preview(
    page:      int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    user: dict = Depends(require_head_of_school),
):
    """Return a paginated slice of the currently loaded attendance table."""
    if _ATTENDANCE is None or _ATTENDANCE.empty:
        return {
            "total": 0, "page": page, "page_size": page_size,
            "total_pages": 0, "columns": [], "data": [],
        }
    total       = len(_ATTENDANCE)
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    start       = (page - 1) * page_size
    page_df     = _ATTENDANCE.iloc[start: start + page_size]
    return {
        "total":       total,
        "page":        page,
        "page_size":   page_size,
        "total_pages": total_pages,
        "columns":     list(_ATTENDANCE.columns),
        "data":        page_df.fillna("").to_dict("records"),
    }

# ─────────────────────────────────────────────────────────────────────────────
# Dashboard Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/dashboard/summary", tags=["Dashboard"])
async def dashboard_summary(
    subject:    Optional[str] = Query(None),
    trimester:  Optional[str] = Query(None),
    year:       Optional[str] = Query(None),
    classgroup: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """Return KPI summary metrics for the selected scope and role."""
    empty = {
        "total_students": 0, "total_subjects": 0, "avg_mark": 0.0,
        "avg_mark_prev": None, "pass_rate": 0.0, "pass_rate_prev": None,
        "at_risk_count": 0, "countries_count": 0,
    }
    if _DATA is None or _DATA.empty:
        return empty

    df = _query_filter(_role_filter(_DATA.copy(), user), subject, trimester, year, classgroup)
    df = df.dropna(subset=["MARKPERCENT"])
    if df.empty:
        return empty

    avg_mark  = _safe(df["MARKPERCENT"].mean())
    pass_rate = _safe((df["MARKPERCENT"] >= 50).mean() * 100)
    countries = (
        int(df["COUNTRY_MASKED"].nunique())
        if user.get("role") in {"Head of Technology", "Head of School"}
        and "COUNTRY_MASKED" in df.columns
        else 0
    )

    # Previous trimester change (only meaningful when a specific trimester is selected)
    avg_mark_prev = pass_rate_prev = None
    if trimester:
        prev = _prev_period(trimester)
        if prev:
            df_p = _query_filter(
                _role_filter(_DATA.copy(), user), subject, prev, None, classgroup
            )
            df_p = df_p.dropna(subset=["MARKPERCENT"])
            if not df_p.empty:
                avg_mark_prev  = _safe(df_p["MARKPERCENT"].mean())
                pass_rate_prev = _safe((df_p["MARKPERCENT"] >= 50).mean() * 100)

    return {
        "total_students":  int(df["STUDENTID_MASKED"].nunique()) if "STUDENTID_MASKED" in df.columns else 0,
        "total_subjects":  int(df["SUBJECTCODE"].nunique())      if "SUBJECTCODE"      in df.columns else 0,
        "avg_mark":        round(avg_mark,       1) if avg_mark       is not None else 0.0,
        "avg_mark_prev":   round(avg_mark_prev,  1) if avg_mark_prev  is not None else None,
        "pass_rate":       round(pass_rate,      1) if pass_rate      is not None else 0.0,
        "pass_rate_prev":  round(pass_rate_prev, 1) if pass_rate_prev is not None else None,
        "at_risk_count":   int((df["MARKPERCENT"] < 50).sum()),
        "countries_count": countries,
    }


@app.get("/api/dashboard/grade-distribution", tags=["Dashboard"])
async def grade_distribution(
    subject:    Optional[str] = Query(None),
    trimester:  Optional[str] = Query(None),
    year:       Optional[str] = Query(None),
    classgroup: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """Return count of students in each 10-point grade band."""
    if _DATA is None or _DATA.empty:
        return {"data": [{"band": b, "count": 0} for b, _, _ in GRADE_BANDS]}

    df = _query_filter(_role_filter(_DATA.copy(), user), subject, trimester, year, classgroup)
    df = df.dropna(subset=["MARKPERCENT"])

    result = []
    for band, lo, hi in GRADE_BANDS:
        count = int(((df["MARKPERCENT"] >= lo) & (df["MARKPERCENT"] <= hi)).sum())
        result.append({"band": band, "count": count})
    return {"data": result}


@app.get("/api/dashboard/performance-trend", tags=["Dashboard"])
async def performance_trend(
    subject:    Optional[str] = Query(None),
    classgroup: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """Return per-period average marks for both institution-wide and the selected subject."""
    if _DATA is None or _DATA.empty:
        return {
            "data": [
                {"period": p, "institution_avg": None, "subject_avg": None}
                for p in PERIODS_ORDER
            ]
        }

    df_full = _DATA.dropna(subset=["MARKPERCENT"])
    df_role = _role_filter(_DATA.copy(), user)
    if subject and "SUBJECTCODE" in df_role.columns:
        df_role = df_role[df_role["SUBJECTCODE"] == subject]
    if classgroup and "CLASSGROUP" in df_role.columns:
        df_role = df_role[df_role["CLASSGROUP"] == classgroup]
    df_role = df_role.dropna(subset=["MARKPERCENT"])

    inst_mean = df_full.groupby("STUDYPERIOD")["MARKPERCENT"].mean()
    subj_mean = df_role.groupby("STUDYPERIOD")["MARKPERCENT"].mean()

    result = []
    for period in PERIODS_ORDER:
        inst = _safe(inst_mean.get(period))
        subj = _safe(subj_mean.get(period))
        result.append({
            "period":          period,
            "institution_avg": round(inst, 1) if inst is not None else None,
            "subject_avg":     round(subj, 1) if subj is not None else None,
        })
    return {"data": result}


@app.get("/api/dashboard/assessment-comparison", tags=["Dashboard"])
async def assessment_comparison(
    subject:    Optional[str] = Query(None),
    trimester:  Optional[str] = Query(None),
    year:       Optional[str] = Query(None),
    classgroup: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """Return average mark and pass rate grouped by assessment type."""
    if _DATA is None or "ASSESSMENTTYPECODE" not in _DATA.columns:
        return {"data": []}

    df = _query_filter(_role_filter(_DATA.copy(), user), subject, trimester, year, classgroup)
    df = df.dropna(subset=["MARKPERCENT", "ASSESSMENTTYPECODE"])

    grp   = df.groupby("ASSESSMENTTYPECODE")["MARKPERCENT"]
    avg_s = grp.mean().round(1)
    pr_s  = grp.apply(lambda x: round((x >= 50).mean() * 100, 1))
    items = [
        {"type": t, "avg_mark": float(avg_s[t]), "pass_rate": float(pr_s[t])}
        for t in avg_s.index
    ]
    return {"data": items, "items": items}


@app.get("/api/dashboard/pass-fail", tags=["Dashboard"])
async def pass_fail(
    subject:    Optional[str] = Query(None),
    trimester:  Optional[str] = Query(None),
    year:       Optional[str] = Query(None),
    classgroup: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """Return raw pass/fail counts and pass rate percentage."""
    if _DATA is None or _DATA.empty:
        return {"pass_count": 0, "fail_count": 0, "pass_rate": 0.0}

    df = _query_filter(_role_filter(_DATA.copy(), user), subject, trimester, year, classgroup)
    df = df.dropna(subset=["MARKPERCENT"])

    pass_count = int((df["MARKPERCENT"] >= 50).sum())
    fail_count = int((df["MARKPERCENT"] <  50).sum())
    total      = pass_count + fail_count
    return {
        "pass_count": pass_count,
        "fail_count": fail_count,
        "pass_rate":  round(pass_count / total * 100, 1) if total > 0 else 0.0,
        "breakdown":  [{"status": "Pass", "count": pass_count}, {"status": "Fail", "count": fail_count}],
    }


@app.get("/api/dashboard/international", tags=["Dashboard"])
async def international_performance(
    trimester: Optional[str] = Query(None),
    year:      Optional[str] = Query(None),
    user: dict = Depends(require_head_of_school),
):
    """Return average mark per country of origin (admin only)."""
    if _DATA is None or "COUNTRY_MASKED" not in _DATA.columns:
        return {"data": []}

    df = _query_filter(_DATA.copy(), trimester=trimester, year=year)
    df = df.dropna(subset=["MARKPERCENT", "COUNTRY_MASKED"])

    grouped = df.groupby("COUNTRY_MASKED")["MARKPERCENT"].mean().round(1).reset_index()
    grouped.columns = ["country", "avg_mark"]
    grouped = grouped.sort_values("avg_mark", ascending=False)
    return {"data": grouped.to_dict("records")}


@app.get("/api/dashboard/difficulty-index", tags=["Dashboard"])
async def difficulty_index(user: dict = Depends(require_head_of_school)):
    """Return failure rate per subject sorted descending (admin only)."""
    if _DATA is None or "SUBJECTCODE" not in _DATA.columns:
        return {"data": []}

    df = _DATA.dropna(subset=["MARKPERCENT"]).copy()
    df["_fail"] = (df["MARKPERCENT"] < 50).astype(int)
    result = df.groupby("SUBJECTCODE")["_fail"].mean().mul(100).round(1).reset_index()
    result.columns = ["subject", "failure_rate"]
    result = result.sort_values("failure_rate", ascending=False)
    return {"data": result.to_dict("records")}


@app.get("/api/dashboard/classgroups", tags=["Dashboard"])
async def get_classgroups(
    subject: Optional[str] = Query(None),
    user: dict = Depends(require_head_of_school),
):
    """Return the distinct class-group values for the given subject."""
    if _DATA is None or "CLASSGROUP" not in _DATA.columns:
        return {"classgroups": []}
    df = _DATA.copy()
    if subject and "SUBJECTCODE" in df.columns:
        df = df[df["SUBJECTCODE"] == subject]
    return {"classgroups": sorted(df["CLASSGROUP"].dropna().unique().tolist())}


ATTENDANCE_BANDS = [
    ("0-49%",  0.0,  0.4999),
    ("50-59%", 0.5,  0.5999),
    ("60-69%", 0.6,  0.6999),
    ("70-79%", 0.7,  0.7999),
    ("80-89%", 0.8,  0.8999),
    ("90-100%", 0.9, 1.0),
]

# _ATTENDANCE has two genuinely different populations layered in one table, and
# every endpoint reading it must say explicitly which one it's using — silently
# mixing them under one generic "attendance" label is exactly how a 5,536-row
# mismatch (84,422 vs 78,886) went unlabelled between two dashboard numbers
# that looked like they should describe the same thing. ALL_TRACKED is every
# enrolment with attendance data for a real capstone subject+period (some of
# these students attended classes but have zero assessment rows recorded for
# that exact subject+period — early withdrawal or a cross-system data gap, not
# a bug — that's real, informative attendance data and dropping it would throw
# information away). WITH_OUTCOME is the strict subset that also has a real
# PASS/FAIL target, the only population an attendance-vs-outcome comparison
# can honestly be computed on.
POPULATION_ALL_TRACKED  = (
    "all attendance-tracked enrolments (course+period+year filtered) — includes "
    "students with no matching capstone assessment record for that subject+period"
)
POPULATION_WITH_OUTCOME = "enrolments with BOTH attendance data AND a matching capstone assessment record (a real PASS/FAIL target)"


@app.get("/api/dashboard/attendance-distribution", tags=["Dashboard"])
async def attendance_distribution(
    subject:   Optional[str] = Query(None),
    trimester: Optional[str] = Query(None),
    year:      Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """Return count of enrolments in each attendance-rate band.

    Population: ALL attendance-tracked enrolments, not restricted to those with
    a matching assessment record — see POPULATION_ALL_TRACKED.
    """
    if _ATTENDANCE is None or _ATTENDANCE.empty:
        return {"data": [{"band": b, "count": 0} for b, _, _ in ATTENDANCE_BANDS], "population": POPULATION_ALL_TRACKED, "n": 0}

    df = _query_filter(_role_filter(_ATTENDANCE.copy(), user), subject, trimester, year)
    df = df.dropna(subset=["ATTENDANCE_RATE"])

    result = []
    for band, lo, hi in ATTENDANCE_BANDS:
        count = int(((df["ATTENDANCE_RATE"] >= lo) & (df["ATTENDANCE_RATE"] <= hi)).sum())
        result.append({"band": band, "count": count})
    return {
        "data": result,
        "mean_attendance_rate": _safe(round(df["ATTENDANCE_RATE"].mean() * 100, 1)) if not df.empty else None,
        "population": POPULATION_ALL_TRACKED,
        "n": int(len(df)),
    }


@app.get("/api/dashboard/attendance-outcome", tags=["Dashboard"])
async def attendance_outcome(
    subject:   Optional[str] = Query(None),
    trimester: Optional[str] = Query(None),
    year:      Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """Return attendance-rate vs pass/fail outcome correlation for the current scope.

    Population: only enrolments with a matching assessment record — see
    POPULATION_WITH_OUTCOME.
    """
    empty = {"correlation": None, "mean_attendance_pass": None, "mean_attendance_fail": None, "n": 0, "population": POPULATION_WITH_OUTCOME}
    if _ATTENDANCE is None or _ATTENDANCE.empty or "PASS" not in _ATTENDANCE.columns:
        return empty

    df = _query_filter(_role_filter(_ATTENDANCE.copy(), user), subject, trimester, year)
    df = df.dropna(subset=["ATTENDANCE_RATE", "PASS"])
    if df.empty:
        return empty

    corr = df["ATTENDANCE_RATE"].corr(df["PASS"])
    return {
        "correlation":          _safe(round(corr, 3)) if corr is not None else None,
        "mean_attendance_pass": _safe(round(df.loc[df["PASS"] == 1, "ATTENDANCE_RATE"].mean() * 100, 1)),
        "mean_attendance_fail": _safe(round(df.loc[df["PASS"] == 0, "ATTENDANCE_RATE"].mean() * 100, 1)),
        "n": int(len(df)),
        "population": POPULATION_WITH_OUTCOME,
    }


@app.get("/api/dashboard/attendance-by-subject", tags=["Dashboard"])
async def attendance_by_subject(user: dict = Depends(get_current_user)):
    """Return average attendance rate per subject, sorted ascending.

    Admin sees all subjects; Lecturer sees only their assigned subjects (via
    _role_filter). Population: ALL attendance-tracked enrolments — see
    POPULATION_ALL_TRACKED.
    """
    if _ATTENDANCE is None or _ATTENDANCE.empty or "SUBJECTCODE" not in _ATTENDANCE.columns:
        return {"data": [], "population": POPULATION_ALL_TRACKED}

    df = _role_filter(_ATTENDANCE.copy(), user).dropna(subset=["ATTENDANCE_RATE"])
    result = (
        df.groupby("SUBJECTCODE")["ATTENDANCE_RATE"]
        .agg(["mean", "count"])
        .reset_index()
        .rename(columns={"mean": "avg_attendance_rate", "count": "n"})
    )
    result["avg_attendance_rate"] = (result["avg_attendance_rate"] * 100).round(1)
    result = result.sort_values("avg_attendance_rate")
    return {"data": result.to_dict("records"), "population": POPULATION_ALL_TRACKED}

# ─────────────────────────────────────────────────────────────────────────────
# Explorer Routes
# ─────────────────────────────────────────────────────────────────────────────

def _str_val(val) -> str:
    """Convert a pandas cell value to str, coercing NaN → empty string."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return ""
    return str(val)


def _attach_attendance_rate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Join ATTENDANCE_RATE onto a row-level (per-assessment-item) DataFrame at
    the student-subject-period level — one attendance rate per record,
    matching that record's enrolment, not a new per-session breakdown (this
    is Explorer, which is assessment-record-level, not session-level).
    Rows with no matching attendance data (or if _ATTENDANCE never loaded)
    get ATTENDANCE_RATE = NaN, handled downstream via _safe().
    """
    if _ATTENDANCE is None or _ATTENDANCE.empty or "ATTENDANCE_RATE" not in _ATTENDANCE.columns:
        df = df.copy()
        df["ATTENDANCE_RATE"] = None
        return df
    att_keys = _ATTENDANCE[["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD", "ATTENDANCE_RATE"]]
    return df.merge(att_keys, on=["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"], how="left")


def _explorer_filter(
    df:               pd.DataFrame,
    subject:          Optional[str] = None,
    assessment_type:  Optional[str] = None,
    passed:           Optional[str] = None,
    trimester:        Optional[str] = None,
    search:           Optional[str] = None,
    country:          Optional[str] = None,
    gender:           Optional[str] = None,
    age_group:        Optional[str] = None,
    is_admin:         bool           = False,
    attendance_band:  Optional[str] = None,
) -> pd.DataFrame:
    """Apply Explorer-specific filters including admin-only demographic filters."""
    if "MARKPERCENT" in df.columns:
        df = df.dropna(subset=["MARKPERCENT"])
    if subject and "SUBJECTCODE" in df.columns:
        df = df[df["SUBJECTCODE"] == subject]
    if assessment_type and "ASSESSMENTTYPECODE" in df.columns:
        df = df[df["ASSESSMENTTYPECODE"] == assessment_type]
    if passed == "true":
        df = df[df["MARKPERCENT"] >= 50]
    elif passed == "false":
        df = df[df["MARKPERCENT"] < 50]
    if trimester and "STUDYPERIOD" in df.columns:
        df = df[df["STUDYPERIOD"] == trimester]
    if search and "STUDENTID_MASKED" in df.columns:
        df = df[df["STUDENTID_MASKED"].astype(str).str.contains(search, case=False, na=False)]
    if attendance_band and "ATTENDANCE_RATE" in df.columns:
        if attendance_band == "low":
            df = df[df["ATTENDANCE_RATE"] < 0.5]
        elif attendance_band == "medium":
            df = df[(df["ATTENDANCE_RATE"] >= 0.5) & (df["ATTENDANCE_RATE"] < 0.8)]
        elif attendance_band == "high":
            df = df[df["ATTENDANCE_RATE"] >= 0.8]
    if is_admin:
        if country and "COUNTRY_MASKED" in df.columns:
            df = df[df["COUNTRY_MASKED"] == country]
        if gender and "GENDERCODE" in df.columns:
            df = df[df["GENDERCODE"] == gender]
        if age_group and "AGEGROUP" in df.columns:
            df = df[df["AGEGROUP"] == age_group]
    return df


def _row_to_record(row: dict, is_admin: bool) -> dict:
    """Convert a raw DataFrame row dict to the Explorer API record shape."""
    mp = row.get("MARKPERCENT")
    try:
        passed = bool(float(mp) >= 50) if mp is not None else False
    except (TypeError, ValueError):
        passed = False
    att_rate = _safe(row.get("ATTENDANCE_RATE"))
    record: dict = {
        "student_id":      _str_val(row.get("STUDENTID_MASKED")),
        "subject":         _str_val(row.get("SUBJECTCODE")),
        "assessment_type": _str_val(row.get("ASSESSMENTTYPECODE")),
        "study_period":    _str_val(row.get("STUDYPERIOD")),
        "mark_percent":    _safe(mp),
        "assessment_mark": _safe(row.get("ASSESSMENTMARK")),
        "max_mark":        _safe(row.get("MAXMARK")),
        "weighting":       _safe(row.get("WEIGHTING")),
        "passed":          passed,
        "attendance_rate": round(att_rate * 100, 1) if att_rate is not None else None,
    }
    if is_admin:
        record["country"]   = _str_val(row.get("COUNTRY_MASKED"))
        record["gender"]    = _str_val(row.get("GENDERCODE"))
        record["age_group"] = _str_val(row.get("AGEGROUP"))
    return record


@app.get("/api/explorer/records", tags=["Explorer"])
async def explorer_records(
    page:            int           = Query(1, ge=1),
    page_size:       int           = Query(50, ge=1, le=500),
    subject:         Optional[str] = Query(None),
    assessment_type: Optional[str] = Query(None),
    passed:          Optional[str] = Query(None),
    trimester:       Optional[str] = Query(None),
    search:          Optional[str] = Query(None),
    country:         Optional[str] = Query(None),
    gender:          Optional[str] = Query(None),
    age_group:       Optional[str] = Query(None),
    attendance_band: Optional[str] = Query(None, description="low (<50%) / medium (50-79%) / high (80%+)"),
    user: dict = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """Return a paginated, filtered list of student assessment records."""
    if _DATA is None or _DATA.empty:
        return {"total": 0, "page": page, "page_size": page_size, "total_pages": 0, "data": []}

    is_admin = user.get("role") in {"Head of Technology", "Head of School"}
    df = _role_filter(_DATA.copy(), user)
    df = _attach_attendance_rate(df)
    df = _explorer_filter(
        df, subject, assessment_type, passed, trimester,
        search, country, gender, age_group, is_admin, attendance_band,
    )

    total       = len(df)
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    start       = (page - 1) * page_size
    page_df     = df.iloc[start: start + page_size]

    if any([subject, assessment_type, passed, trimester, search, country, gender, age_group, attendance_band]):
        await _append_audit_db(db, user_uid=user["sub"], action_type="Data Access",
                               status="Success", detail="Explorer records viewed")
    return {
        "total":       total,
        "page":        page,
        "page_size":   page_size,
        "total_pages": total_pages,
        "data":        [_row_to_record(r, is_admin) for r in page_df.to_dict("records")],
    }


@app.get("/api/explorer/filters", tags=["Explorer"])
async def explorer_filters(user: dict = Depends(get_current_user)):
    """Return available filter values for subjects, trimesters, and demographic options."""
    is_admin = user.get("role") in {"Head of Technology", "Head of School"}

    if _DATA is None or _DATA.empty:
        return {
            "subjects":         user.get("subjects", []) if not is_admin else [],
            "assessment_types": [], "trimesters": [],
            "countries":        [], "genders":    [], "age_groups": [],
        }

    df_role = _role_filter(_DATA.copy(), user)

    subjects = (
        sorted(df_role["SUBJECTCODE"].dropna().unique().tolist())
        if "SUBJECTCODE" in df_role.columns else []
    )
    assessment_types = (
        sorted(df_role["ASSESSMENTTYPECODE"].dropna().unique().tolist())
        if "ASSESSMENTTYPECODE" in df_role.columns else []
    )
    trimesters = [
        p for p in PERIODS_ORDER
        if "STUDYPERIOD" in df_role.columns and p in df_role["STUDYPERIOD"].values
    ]

    countries  = (
        sorted(_DATA["COUNTRY_MASKED"].dropna().unique().tolist())
        if is_admin and "COUNTRY_MASKED" in _DATA.columns else []
    )
    genders    = (
        sorted(_DATA["GENDERCODE"].dropna().unique().tolist())
        if is_admin and "GENDERCODE" in _DATA.columns else []
    )
    age_groups = (
        sorted(_DATA["AGEGROUP"].dropna().unique().tolist())
        if is_admin and "AGEGROUP" in _DATA.columns else []
    )

    return {
        "subjects":         subjects,
        "assessment_types": assessment_types,
        "trimesters":       trimesters,
        "countries":        countries,
        "genders":          genders,
        "age_groups":       age_groups,
    }


@app.get("/api/explorer/student/{student_id}", tags=["Explorer"])
async def explorer_student(
    student_id:   str,
    subject:      Optional[str] = Query(None),
    study_period: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """Return full assessment history, trend, and peer comparison for a single student."""
    if _DATA is None or "STUDENTID_MASKED" not in _DATA.columns:
        raise HTTPException(404, "Student not found")

    is_admin = user.get("role") in {"Head of Technology", "Head of School"}
    df = _role_filter(_DATA.copy(), user)
    df = df[df["STUDENTID_MASKED"].astype(str) == str(student_id)]
    if subject and "SUBJECTCODE" in df.columns:
        df = df[df["SUBJECTCODE"] == subject]
    if study_period and "STUDYPERIOD" in df.columns:
        df = df[df["STUDYPERIOD"] == study_period]
    df = df.dropna(subset=["MARKPERCENT"])

    if df.empty:
        raise HTTPException(404, "Student not found or not in your scope")

    avg_mark       = _safe(df["MARKPERCENT"].mean())
    overall_passed = bool(float(avg_mark) >= 50) if avg_mark is not None else False
    records        = [_row_to_record(r, is_admin) for r in df.to_dict("records")]

    # Per-period trend
    trend_grp = df.groupby("STUDYPERIOD")["MARKPERCENT"].mean().round(1)
    trend = [
        {"period": p, "mark": _safe(trend_grp.get(p))}
        for p in PERIODS_ORDER if p in trend_grp.index
    ]

    # Peer comparison
    subject_codes = (
        df["SUBJECTCODE"].dropna().unique().tolist() if "SUBJECTCODE" in df.columns else []
    )
    df_class = _role_filter(_DATA.copy(), user)
    if subject_codes and "SUBJECTCODE" in df_class.columns:
        df_class = df_class[df_class["SUBJECTCODE"].isin(subject_codes)]
    df_class  = df_class.dropna(subset=["MARKPERCENT"])
    class_avg = _safe(df_class["MARKPERCENT"].mean())

    peer: dict = {
        "student_avg": round(avg_mark,  1) if avg_mark  is not None else None,
        "class_avg":   round(class_avg, 1) if class_avg is not None else None,
    }
    if is_admin and subject_codes and "SUBJECTCODE" in _DATA.columns:
        df_inst  = _DATA[_DATA["SUBJECTCODE"].isin(subject_codes)].dropna(subset=["MARKPERCENT"])
        inst_avg = _safe(df_inst["MARKPERCENT"].mean())
        peer["institution_avg"] = round(inst_avg, 1) if inst_avg is not None else None

    return {
        "student_id":      student_id,
        "overall_passed":  overall_passed,
        "avg_mark":        round(avg_mark, 1) if avg_mark is not None else None,
        "records":         records,
        "trend":           trend,
        "peer_comparison": peer,
    }


@app.get("/api/explorer/export", tags=["Explorer"])
async def explorer_export(
    subject:         Optional[str] = Query(None),
    assessment_type: Optional[str] = Query(None),
    passed:          Optional[str] = Query(None),
    trimester:       Optional[str] = Query(None),
    search:          Optional[str] = Query(None),
    country:         Optional[str] = Query(None),
    gender:          Optional[str] = Query(None),
    age_group:       Optional[str] = Query(None),
    attendance_band: Optional[str] = Query(None, description="low (<50%) / medium (50-79%) / high (80%+)"),
    user: dict = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """Stream a filtered dataset as a CSV download and write an export audit event."""
    if _DATA is None or _DATA.empty:
        raise HTTPException(404, "No data loaded")

    df = _attach_attendance_rate(_DATA.copy())
    df = _explorer_filter(
        df, subject, assessment_type, passed, trimester,
        search, country, gender, age_group, is_admin=True, attendance_band=attendance_band,
    )

    filters_used = [f"{k}={v}" for k, v in [
        ("subject", subject), ("assessment_type", assessment_type),
        ("passed",  passed),  ("trimester",       trimester),
        ("country", country), ("gender",           gender),
        ("age_group", age_group), ("attendance_band", attendance_band),
    ] if v]
    filter_str = ", ".join(filters_used) or "none"

    await _append_audit_db(
        db, user_uid=user["sub"], action_type="Export", status="Success",
        detail=f"Exported {len(df):,} records with filters: {filter_str}",
    )

    if "ATTENDANCE_RATE" in df.columns:
        df = df.copy()
        df["ATTENDANCE_RATE"] = (df["ATTENDANCE_RATE"] * 100).round(1)  # match MARKPERCENT's 0-100 scale, not raw 0-1

    buf   = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    fname = f"edapt_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )

# ─────────────────────────────────────────────────────────────────────────────
# Predict Routes
# ─────────────────────────────────────────────────────────────────────────────

async def _gemini_call(model, prompt: str) -> tuple[str, int]:
    """Run a synchronous Gemini SDK call in a thread pool. Returns (text, tokens)."""
    if model is None:
        return "AI insight unavailable.", 0
    try:
        response = await asyncio.to_thread(model.generate_content, prompt)
        text     = response.text.strip()
        tokens   = getattr(getattr(response, "usage_metadata", None), "total_token_count", 0)
        _GEMINI_TOKEN_LOG.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tokens":    int(tokens),
            "model":     getattr(model, "model_name", "unknown"),
        })
        return text, int(tokens)
    except ResourceExhausted:
        return "Gemini rate limit reached. Please wait 60 seconds before requesting another insight.", 0
    except Exception as _e:
        if "429" in str(_e) or "rate limit" in str(_e).lower() or "quota" in str(_e).lower():
            return "Gemini rate limit reached. Please wait 60 seconds before requesting another insight.", 0
        return "AI insight unavailable.", 0


@app.post("/api/predict", tags=["ML"])
async def predict_outcome(
    req:  PredictRequest,
    user: dict = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """Run the ML ensemble and return a pass-probability prediction."""
    from app.ml.predictor import (
        predict as ml_predict,
        predict_partial as ml_predict_partial,
        compute_partial_score,
        classify_coverage,
        MIN_COVERAGE_FOR_PREDICTION,
    )

    is_admin  = user.get("role") in {"Head of Technology", "Head of School"}
    subj_list = user.get("subjects", [])

    if not is_admin and req.subject not in subj_list:
        raise HTTPException(403, "You are not assigned to that subject.")

    # Always derive from subject_reliability.json directly — _SAFE_SUBJECTS is the
    # model's *training* subject list (fully_clean + mostly_clean) and is not a
    # reliable proxy for "no warning needed": a mostly_clean subject is safe to
    # train on but should still show the yellow warning below.
    reliability = _subject_reliability_category(req.subject)
    if reliability == "unreliable":
        return {
            "subject":              req.subject,
            "prediction_available": False,
            "message": (
                "Prediction unavailable for this subject due to incomplete "
                "assessment data. Contact your Head of Technology."
            ),
        }

    assessments_used_dicts = [a.model_dump() for a in req.assessments_used]

    # Coverage tier decides which model serves this request — never trust
    # req.total_weight_recorded for this decision, only the raw items actually
    # submitted, for the same reason partial_weighted_score is never trusted
    # directly (a client could misreport how complete a record is).
    cumulative_weighting_recorded = sum(a["weighting"] for a in assessments_used_dicts)
    coverage_tier = classify_coverage(cumulative_weighting_recorded)

    if coverage_tier == "insufficient":
        # A coverage gate, not a data-quality gate — distinct message from the
        # unreliable-subject case above, even though the response shape (
        # prediction_available: False) matches so the frontend can reuse the
        # same red-panel pattern for both.
        return {
            "subject":              req.subject,
            "prediction_available": False,
            "coverage_status":      "insufficient_data",
            "message": (
                f"Not enough assessment data recorded yet to generate a prediction "
                f"({cumulative_weighting_recorded:.0f}% of the term recorded — at least "
                f"{MIN_COVERAGE_FOR_PREDICTION:.0f}% is needed). Check back once more "
                f"assessments have been marked."
            ),
        }

    # attendance_rate: an explicitly-supplied value (What-If specifying one)
    # always wins. Otherwise resolve it through _resolve_attendance_rate — the
    # SAME function the roster uses — so a real, identified student gets their
    # own real attendance rate here, not the subject average. This endpoint
    # used to ignore req.student_id entirely and go straight to the subject
    # average, which meant the detail view and the roster reported different
    # attendance for the same person; see _resolve_attendance_rate's docstring.
    # The tier matters: a mid-term prediction must be truncated to this
    # student's current coverage, never scored against their final attendance.
    if req.attendance_rate is not None:
        attendance_rate, attendance_rate_is_default = req.attendance_rate, False
    else:
        if coverage_tier == "complete":
            coverage_fraction = None
        else:
            total_weight = _period_total_weight(req.subject, req.study_period)
            coverage_fraction = (
                cumulative_weighting_recorded / total_weight if total_weight else 0.0
            )
        attendance_rate, attendance_rate_is_default = _resolve_attendance_rate(
            req.student_id, req.subject, req.study_period, coverage_fraction
        )

    if coverage_tier == "complete":
        # ── UNCHANGED — existing top-2, best_model.pkl path. Do not touch. ──
        # req.partial_weighted_score / req.partial_weight_coverage are accepted for
        # backward compatibility but never trusted — a client summing ALL entered
        # assessments (not just the top 2 by weight) would silently feed the model
        # a feature value outside its training distribution. Always recompute
        # server-side from the raw assessments_used, using the same top-2-by-weight
        # logic train_model.py's build_early_features() uses, so training and
        # serving can't drift apart regardless of what the client sends.
        partial_weighted_score, partial_weight_coverage = compute_partial_score(assessments_used_dicts)
        result = ml_predict(
            subject=                 req.subject,
            study_period=            req.study_period,
            trimester_num=           req.trimester_num,
            assess1_mark=            req.assess1_mark,
            assess1_weight=          req.assess1_weight,
            assess1_contribution=    req.assess1_contribution,
            assess2_mark=            req.assess2_mark,
            assess2_weight=          req.assess2_weight,
            assess2_contribution=    req.assess2_contribution,
            partial_weighted_score=  partial_weighted_score,
            partial_weight_coverage= partial_weight_coverage,
            num_assessments=         req.num_assessments,
            total_weight_recorded=   req.total_weight_recorded,
            weight_complete=         req.weight_complete,
            assessments_used=        assessments_used_dicts,
            attendance_rate=         attendance_rate,
        )
    else:  # "partial" — 50-99% coverage, genuinely mid-term
        result = ml_predict_partial(
            subject=          req.subject,
            study_period=     req.study_period,
            trimester_num=    req.trimester_num,
            assessments_used= assessments_used_dicts,
            attendance_rate=  attendance_rate,
        )

    if "error" in result:
        # Two genuinely different failures used to collapse into one misleading
        # 503 saying "ML model not loaded. Run train_model.py first."
        #
        #   1. A required FEATURE was unavailable for this specific request.
        #      Reproduced: a subject with no attendance rows at all yields no
        #      per-student rate and no subject average, so ATTENDANCE_RATE is
        #      None and the 11-feature live model cannot be called. The model is
        #      loaded and healthy; this one prediction lacks an input. Telling a
        #      lecturer to "run train_model.py" is wrong advice for a data gap,
        #      and a 503 tells the frontend the service is down when it isn't.
        #
        #   2. No model is actually loaded. That IS a 503.
        #
        # The fix deliberately does NOT invent an attendance value. Substituting
        # a global mean or a zero would produce a confident-looking probability
        # from a fabricated input, which is worse than saying "not enough data" —
        # this project already treats a missing input as a reason to decline
        # (see the insufficient_data coverage gate above), not to guess.
        #
        # Falling back to a 10-feature model was considered and rejected: no
        # 10-feature model is live, so it would mean loading a superseded,
        # ungated version at serving time and silently serving predictions from
        # a model nobody promoted — exactly what the promotion gate exists to
        # prevent.
        error_text = str(result["error"])
        if error_text.startswith("missing_required_feature"):
            missing_feature = error_text.split(":", 1)[1].split(" is required")[0].strip()
            return {
                "subject":              req.subject,
                "prediction_available": False,
                "data_status":          "missing_required_data",
                "missing_feature":      missing_feature,
                "message": (
                    f"Not enough data to generate a prediction: this subject has no "
                    f"{missing_feature.replace('_', ' ').lower()} recorded, which the "
                    f"current model requires. This is a data gap, not a system fault — "
                    f"the prediction service is running normally."
                ),
            }
        raise HTTPException(503, "ML model is not loaded. Run train_model.py first.")

    result["attendance_rate_is_default"] = attendance_rate_is_default and result.get("attendance_rate_used") is not None

    # "What would help most" — derived from the SHAP explanation already
    # computed above, never a second model call. Only meaningful for a real
    # identified student: for a hypothetical What-If scenario there is no one
    # to advise, so it is omitted rather than invented.
    if req.student_id:
        result["top_actionable_factor"] = top_actionable_factor(result.get("shap_explanation"))
        result["excluded_factors"] = excluded_factor_summary(result.get("shap_explanation"))

    if reliability == "mostly_clean":
        result["reliability_warning"] = (
            "This subject's data was only partially verified during cleaning — "
            "assessment weightings may be incomplete."
        )

    # Log the actual server-computed features alongside the outcome — not just
    # subject+probability — so any future train/serve discrepancy can be
    # reconstructed exactly from history instead of only bounded by mechanism
    # (see the partial_weighted_score client/server mismatch this fixed). Pulled
    # from `result` rather than tier-specific locals, since both branches above
    # populate the same partial_weighted_score/total_weight_recorded keys.
    audit_features = json.dumps({
        "coverage_tier":           coverage_tier,
        "assessments_used":        assessments_used_dicts,
        "partial_weighted_score":  result.get("partial_weighted_score"),
        "partial_weight_coverage": (result.get("total_weight_recorded") or 0) / 100,
    })
    await _append_audit_db(db, user_uid=user["sub"], action_type="Prediction Run",
                           status="Success",
                           detail=(f"Predicted {result['subject']}: {result['probability']}% pass probability "
                                   f"| features: {audit_features}"))

    # Only when this call is identified to a real student — a what-if scenario
    # (no student_id) has nothing to reconcile against later and correctly
    # logs no prediction row.
    if req.student_id:
        await _upsert_prediction(
            db,
            student_id_masked = req.student_id,
            subject_code       = req.subject,
            study_period        = req.study_period,
            result              = result,
        )

    return result

# ─────────────────────────────────────────────────────────────────────────────
# Gemini Routes
# ─────────────────────────────────────────────────────────────────────────────

def _subject_stats(subject: Optional[str], trimester: Optional[str], user: dict) -> dict:
    """Build summary stats for a subject/trimester scope."""
    if _DATA is None or _DATA.empty:
        return {}
    df = _role_filter(_DATA.copy(), user)
    df = df.dropna(subset=["MARKPERCENT"])
    if subject:
        df = df[df["SUBJECTCODE"] == subject]
    if trimester:
        df = df[df["STUDYPERIOD"] == trimester]
    if df.empty:
        return {}

    avg_mark  = round(float(df["MARKPERCENT"].mean()), 1)
    pass_rate = round(float((df["MARKPERCENT"] >= 50).mean() * 100), 1)
    at_risk   = int((df["MARKPERCENT"] < 50).sum())

    if "ASSESSMENTTYPECODE" in df.columns:
        grp     = df.groupby("ASSESSMENTTYPECODE")["MARKPERCENT"].mean()
        weakest = str(grp.idxmin()) if not grp.empty else "N/A"
    else:
        weakest = "N/A"

    prev_pass_rate = None
    if trimester:
        prev = _prev_period(trimester)
        if prev:
            df_p = _role_filter(_DATA.copy(), user)
            df_p = df_p.dropna(subset=["MARKPERCENT"])
            if subject:
                df_p = df_p[df_p["SUBJECTCODE"] == subject]
            df_p = df_p[df_p["STUDYPERIOD"] == prev]
            if not df_p.empty:
                prev_pass_rate = round(float((df_p["MARKPERCENT"] >= 50).mean() * 100), 1)

    breakdown: dict = {}
    if "ASSESSMENTTYPECODE" in df.columns:
        for t, g in df.groupby("ASSESSMENTTYPECODE"):
            breakdown[str(t)] = {
                "avg_mark": round(float(g["MARKPERCENT"].mean()), 1),
                "count":    int(len(g)),
            }

    return {
        "subject":        subject or "All",
        "trimester":      trimester or "All",
        "avg_mark":       avg_mark,
        "pass_rate":      pass_rate,
        "at_risk_count":  at_risk,
        "weakest_type":   weakest,
        "prev_pass_rate": prev_pass_rate,
        "change":         round(pass_rate - prev_pass_rate, 1) if prev_pass_rate is not None else None,
        "breakdown":      breakdown,
    }


def _calc_subject_analytics(subject: str, trimester: Optional[str]) -> dict:
    """Compute full analytics for a single subject, optionally scoped to a trimester."""
    if _DATA is None or "SUBJECTCODE" not in _DATA.columns:
        return {}

    df_all  = _DATA.dropna(subset=["MARKPERCENT"]).copy()
    df_subj = df_all[df_all["SUBJECTCODE"] == subject]
    if df_subj.empty:
        return {}

    df_scope = (
        df_subj[df_subj["STUDYPERIOD"] == trimester]
        if trimester and "STUDYPERIOD" in df_subj.columns else df_subj
    )
    df_inst = (
        df_all[df_all["STUDYPERIOD"] == trimester]
        if trimester and "STUDYPERIOD" in df_all.columns else df_all
    )
    if df_scope.empty:
        return {}

    avg_mark   = round(float(df_scope["MARKPERCENT"].mean()), 1)
    pass_rate  = round(float((df_scope["MARKPERCENT"] >= 50).mean() * 100), 1)
    fail_rate  = round(100.0 - pass_rate, 1)
    stu_count  = (
        int(df_scope["STUDENTID_MASKED"].nunique())
        if "STUDENTID_MASKED" in df_scope.columns else len(df_scope)
    )
    inst_avg = round(float(df_inst["MARKPERCENT"].mean()), 1) if not df_inst.empty else avg_mark
    inst_pr  = (
        round(float((df_inst["MARKPERCENT"] >= 50).mean() * 100), 1)
        if not df_inst.empty else pass_rate
    )
    difficulty = "Low" if fail_rate < 20 else ("Medium" if fail_rate <= 40 else "High")

    prev_avg = prev_pr = None
    if trimester:
        prev = _prev_period(trimester)
        if prev and "STUDYPERIOD" in df_subj.columns:
            df_p = df_subj[df_subj["STUDYPERIOD"] == prev]
            if not df_p.empty:
                prev_avg = round(float(df_p["MARKPERCENT"].mean()), 1)
                prev_pr  = round(float((df_p["MARKPERCENT"] >= 50).mean() * 100), 1)
    else:
        periods_w_data = [
            p for p in PERIODS_ORDER
            if "STUDYPERIOD" in df_subj.columns and p in df_subj["STUDYPERIOD"].values
        ]
        if len(periods_w_data) >= 2:
            df_p = df_subj[df_subj["STUDYPERIOD"] == periods_w_data[-2]]
            if not df_p.empty:
                prev_avg = round(float(df_p["MARKPERCENT"].mean()), 1)
                prev_pr  = round(float((df_p["MARKPERCENT"] >= 50).mean() * 100), 1)

    assessment_breakdown = []
    if "ASSESSMENTTYPECODE" in df_scope.columns:
        grp = df_scope.groupby("ASSESSMENTTYPECODE")["MARKPERCENT"].mean().round(1)
        assessment_breakdown = sorted(
            [{"type": str(t), "avg": round(float(v), 1)} for t, v in grp.items()],
            key=lambda x: x["avg"], reverse=True,
        )

    trimester_comparison = []
    if "STUDYPERIOD" in df_subj.columns:
        for p in PERIODS_ORDER:
            df_p = df_subj[df_subj["STUDYPERIOD"] == p]
            if not df_p.empty:
                pc = (
                    int(df_p["STUDENTID_MASKED"].nunique())
                    if "STUDENTID_MASKED" in df_p.columns else len(df_p)
                )
                trimester_comparison.append({
                    "period":    p,
                    "avg":       round(float(df_p["MARKPERCENT"].mean()), 1),
                    "pass_rate": round(float((df_p["MARKPERCENT"] >= 50).mean() * 100), 1),
                    "count":     pc,
                })

    grade_distribution = []
    for band, lo, hi in GRADE_BANDS:
        s_cnt = int(((df_scope["MARKPERCENT"] >= lo) & (df_scope["MARKPERCENT"] <= hi)).sum())
        i_cnt = (
            int(((df_inst["MARKPERCENT"] >= lo) & (df_inst["MARKPERCENT"] <= hi)).sum())
            if not df_inst.empty else 0
        )
        grade_distribution.append({"band": band, "subject_count": s_cnt, "institution_count": i_cnt})

    performance_trend = []
    if "STUDYPERIOD" in df_subj.columns:
        for p in PERIODS_ORDER:
            df_sp = df_subj[df_subj["STUDYPERIOD"] == p]
            df_ip = df_all[df_all["STUDYPERIOD"]  == p]
            s_avg = round(float(df_sp["MARKPERCENT"].mean()), 1) if not df_sp.empty else None
            i_avg = round(float(df_ip["MARKPERCENT"].mean()), 1) if not df_ip.empty else None
            if s_avg is not None:
                performance_trend.append({"period": p, "subject_avg": s_avg, "institution_avg": i_avg})

    # Attendance — computed from _ATTENDANCE (enrolment-level: one row per
    # student-subject-period), not from df_scope/df_subj (row-level: one row
    # per assessment item) — averaging a per-enrolment rate over row-level
    # data would bias toward enrolments with more recorded assessment items.
    avg_attendance_rate = None
    attendance_trend: list = []
    if _ATTENDANCE is not None and not _ATTENDANCE.empty and "SUBJECTCODE" in _ATTENDANCE.columns:
        att_subj = _ATTENDANCE[_ATTENDANCE["SUBJECTCODE"] == subject]
        att_scope = (
            att_subj[att_subj["STUDYPERIOD"] == trimester]
            if trimester and "STUDYPERIOD" in att_subj.columns else att_subj
        )
        if not att_scope.empty:
            avg_attendance_rate = round(float(att_scope["ATTENDANCE_RATE"].mean() * 100), 1)
        if "STUDYPERIOD" in att_subj.columns:
            for p in PERIODS_ORDER:
                att_sp = att_subj[att_subj["STUDYPERIOD"] == p]
                att_ip = _ATTENDANCE[_ATTENDANCE["STUDYPERIOD"] == p]
                s_avg = round(float(att_sp["ATTENDANCE_RATE"].mean() * 100), 1) if not att_sp.empty else None
                i_avg = round(float(att_ip["ATTENDANCE_RATE"].mean() * 100), 1) if not att_ip.empty else None
                if s_avg is not None:
                    attendance_trend.append({"period": p, "subject_avg": s_avg, "institution_avg": i_avg})

    return {
        "subject":               subject,
        "avg_mark":              avg_mark,
        "pass_rate":             pass_rate,
        "failure_rate":          fail_rate,
        "student_count":         stu_count,
        "institution_avg":       inst_avg,
        "institution_pass_rate": inst_pr,
        "difficulty":            difficulty,
        "prev_avg":              prev_avg,
        "prev_pass_rate":        prev_pr,
        "assessment_breakdown":  assessment_breakdown,
        "trimester_comparison":  trimester_comparison,
        "grade_distribution":    grade_distribution,
        "performance_trend":     performance_trend,
        "avg_attendance_rate":   avg_attendance_rate,
        "attendance_trend":      attendance_trend,
    }


def _institution_stats() -> dict:
    """Compute institution-wide summary statistics used by the HoT Gemini endpoints."""
    if _DATA is None or _DATA.empty:
        return {}
    df = _DATA.dropna(subset=["MARKPERCENT"]).copy()
    if df.empty:
        return {}

    overall_avg = round(float(df["MARKPERCENT"].mean()), 1)
    overall_pr  = round(float((df["MARKPERCENT"] >= 50).mean() * 100), 1)
    at_risk     = int((df["MARKPERCENT"] < 50).sum())
    countries   = int(df["COUNTRY_MASKED"].nunique()) if "COUNTRY_MASKED" in df.columns else 0

    latest = None
    if "STUDYPERIOD" in df.columns:
        for p in reversed(PERIODS_ORDER):
            if p in df["STUDYPERIOD"].values:
                latest = p
                break

    df_latest = (
        df[df["STUDYPERIOD"] == latest]
        if latest and "STUDYPERIOD" in df.columns else df
    )
    latest_pr = (
        round(float((df_latest["MARKPERCENT"] >= 50).mean() * 100), 1)
        if not df_latest.empty else overall_pr
    )

    prev_pr = None
    if latest:
        prev = _prev_period(latest)
        if prev and "STUDYPERIOD" in df.columns:
            df_prev = df[df["STUDYPERIOD"] == prev]
            if not df_prev.empty:
                prev_pr = round(float((df_prev["MARKPERCENT"] >= 50).mean() * 100), 1)

    subjects_below: list = []
    if "SUBJECTCODE" in df.columns:
        for subj, grp in df.groupby("SUBJECTCODE"):
            pr = float((grp["MARKPERCENT"] >= 50).mean() * 100)
            if pr < 50:
                subjects_below.append({"subject": str(subj), "pass_rate": round(pr, 1)})
        subjects_below.sort(key=lambda x: x["pass_rate"])

    intl: list = []
    if "COUNTRY_MASKED" in df.columns:
        for country, grp in df.groupby("COUNTRY_MASKED"):
            intl.append({
                "country":  str(country),
                "avg_mark": round(float(grp["MARKPERCENT"].mean()), 1),
            })
        intl.sort(key=lambda x: x["avg_mark"], reverse=True)

    assess: list = []
    if "ASSESSMENTTYPECODE" in df.columns:
        for t, grp in df.groupby("ASSESSMENTTYPECODE"):
            assess.append({
                "type":      str(t),
                "avg_mark":  round(float(grp["MARKPERCENT"].mean()), 1),
                "pass_rate": round(float((grp["MARKPERCENT"] >= 50).mean() * 100), 1),
            })

    return {
        "overall_avg":             overall_avg,
        "overall_pass_rate":       overall_pr,
        "latest_period":           latest or "N/A",
        "latest_pass_rate":        latest_pr,
        "prev_pass_rate":          prev_pr,
        "at_risk_count":           at_risk,
        "countries_count":         countries,
        "subjects_below_50_count": len(subjects_below),
        "subjects_below_50":       [s["subject"] for s in subjects_below[:10]],
        "top_3_failing":           subjects_below[:3],
        "top_3_countries":         intl[:3],
        "assessment_breakdown":    assess,
    }


@app.post("/api/gemini/alert", tags=["Gemini"])
async def gemini_alert(
    req:  GeminiAlertRequest,
    user: dict = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """Generate a one-sentence Gemini alert for the selected subject/trimester."""
    stats = _subject_stats(req.subject, req.trimester, user)
    if not stats:
        return {"alert": "", "tokens_used": 0}

    change_str = f"{stats['change']:+.1f}%" if stats["change"] is not None else "N/A"
    prompt = (
        f"Subject: {stats['subject']}, Current pass rate: {stats['pass_rate']}%, "
        f"Previous: {stats.get('prev_pass_rate', 'N/A')}%, Change: {change_str}. "
        f"Weakest assessment type: {stats['weakest_type']}. "
        "Write ONE alert sentence for a lecturer. Be specific. Mention the subject name and the change."
    )
    alert, tokens = await _gemini_call(_flash_model, prompt)
    await _append_audit_db(db, user_uid=user["sub"], action_type="AI Request",
                           status="Success",
                           detail=f"Gemini alert requested for {req.subject or 'all subjects'}")
    return {"alert": alert, "tokens_used": tokens}


@app.post("/api/gemini/analyse", tags=["Gemini"])
async def gemini_analyse(
    req:  GeminiAnalyseRequest,
    user: dict = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """Generate a 3-4 sentence Gemini analysis for the selected subject/trimester."""
    stats = _subject_stats(req.subject, req.trimester, user)
    if not stats:
        return {"analysis": "No data available for analysis.", "tokens_used": 0, "model": "none"}

    prompt = (
        f"You are an academic analyst. Given these stats for {req.subject} "
        f"in {req.trimester or 'the current period'}: {stats}. "
        "Write a 3-4 sentence analysis for a lecturer. "
        "Be factual. Use the exact numbers provided. Recommend one action."
    )
    analysis, tokens = await _gemini_call(_pro_model, prompt)
    await _append_audit_db(db, user_uid=user["sub"], action_type="AI Request",
                           status="Success",
                           detail=f"Gemini analysis requested for {req.subject}")
    return {"analysis": analysis, "tokens_used": tokens, "model": "gemini-1.5-pro"}


@app.post("/api/gemini/ask", tags=["Gemini"])
async def gemini_ask(
    req:  GeminiAskRequest,
    user: dict = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """Answer a lecturer's free-text question using Gemini with subject context."""
    stats   = _subject_stats(req.subject, req.trimester, user)
    context = stats if stats else {"note": "No data loaded yet."}

    prompt = (
        f"You are an academic analyst for {req.subject or 'the institution'} at KOI. "
        f"Here is the current data: {context}. "
        f"Lecturer question: {req.question}. "
        "Answer in 2-3 sentences using the data provided. Be specific and actionable."
    )
    answer, tokens = await _gemini_call(_pro_model, prompt)
    await _append_audit_db(db, user_uid=user["sub"], action_type="AI Request",
                           status="Success",
                           detail=f"Gemini question asked about {req.subject or 'institution'}")
    return {"answer": answer, "tokens_used": tokens, "model": "gemini-1.5-pro"}


@app.post("/api/gemini/institution-alert", tags=["Gemini"])
async def gemini_institution_alert(
    user: dict = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """Generate a one-sentence institution-wide Gemini alert for the Head of Technology."""
    stats = _institution_stats()
    if not stats:
        return {"alert": "", "tokens_used": 0}
    subj_str = ", ".join(stats["subjects_below_50"][:5]) or "none"
    top3     = ", ".join(
        f"{s['subject']} ({s['pass_rate']}%)" for s in stats["top_3_failing"]
    ) or "none"
    prompt = (
        f"Institution stats: overall pass rate {stats['latest_pass_rate']}% "
        f"in period {stats['latest_period']}, "
        f"{stats['subjects_below_50_count']} subjects below 50%: {subj_str}. "
        f"Top failing: {top3}. "
        "Write ONE alert sentence for the Head of Technology. Name specific subjects. Be direct."
    )
    alert, tokens = await _gemini_call(_flash_model, prompt)
    await _append_audit_db(db, user_uid=user["sub"], action_type="AI Request",
                           status="Success", detail="Institution alert requested")
    return {"alert": alert, "tokens_used": tokens}


@app.post("/api/gemini/institution-analyse", tags=["Gemini"])
async def gemini_institution_analyse(
    user: dict = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """Generate a 4-5 sentence institution-wide Gemini analysis."""
    stats = _institution_stats()
    if not stats:
        return {"analysis": "No data available for analysis.", "tokens_used": 0, "model": "none"}
    prompt = (
        "You are an academic analyst for KOI. "
        f"Institution-wide stats: {stats}. "
        "Write a 4-5 sentence analysis for the Head of Technology. "
        "Be factual, use exact numbers, recommend two specific actions."
    )
    analysis, tokens = await _gemini_call(_pro_model, prompt)
    await _append_audit_db(db, user_uid=user["sub"], action_type="AI Request",
                           status="Success", detail="Institution analysis requested")
    return {"analysis": analysis, "tokens_used": tokens, "model": "gemini-1.5-pro"}


@app.post("/api/gemini/institution-ask", tags=["Gemini"])
async def gemini_institution_ask(
    req:  GeminiInstitutionAskRequest,
    user: dict = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """Answer a Head of Technology question using Gemini with institution-wide context."""
    stats   = _institution_stats()
    context = stats if stats else {"note": "No data loaded yet."}
    prompt  = (
        "You are an academic analyst for KOI. "
        f"Institution context: {context}. "
        f"Head of Technology question: {req.question}. "
        "Answer in 2-3 sentences using the data. Be specific."
    )
    answer, tokens = await _gemini_call(_pro_model, prompt)
    await _append_audit_db(db, user_uid=user["sub"], action_type="AI Request",
                           status="Success", detail="Institution question asked")
    return {"answer": answer, "tokens_used": tokens}


@app.get("/api/gemini/token-log", tags=["Gemini"])
async def gemini_token_log(user: dict = Depends(require_head_of_school)):
    """Return the in-memory Gemini token-usage log (newest first)."""
    return {"data": list(reversed(_GEMINI_TOKEN_LOG)), "total": len(_GEMINI_TOKEN_LOG)}


@app.get("/api/subjects/list", tags=["Subjects"])
async def subjects_list(user: dict = Depends(require_head_of_school)):
    """Return sorted list of all subject codes in the dataset."""
    if _DATA is None or "SUBJECTCODE" not in _DATA.columns:
        return []
    return sorted(_DATA["SUBJECTCODE"].dropna().unique().tolist())


@app.get("/api/subjects/{subject}/assessments", tags=["Subjects"])
async def subject_assessments(
    subject:      str,
    study_period: Optional[str] = Query(None),
    user:         dict = Depends(get_current_user),
):
    """Return unique assessment types and weightings for a subject and period."""
    if _DATA is None or _DATA.empty:
        raise HTTPException(503, "No data loaded. Upload a dataset first.")
    df_subj = _DATA[_DATA["SUBJECTCODE"] == subject]
    if df_subj.empty:
        raise HTTPException(404, "Subject not found.")

    # Always derive from subject_reliability.json directly — see the /api/predict
    # comment above for why _SAFE_SUBJECTS membership isn't a valid shortcut here.
    reliability = _subject_reliability_category(subject)
    if reliability == "unreliable":
        return {
            "subject":              subject,
            "prediction_available": False,
            "message": (
                "Prediction unavailable for this subject due to incomplete "
                "assessment data. Contact your Head of Technology."
            ),
        }

    if study_period is not None:
        df_period = df_subj[df_subj["STUDYPERIOD"] == study_period]
        if df_period.empty:
            raise HTTPException(404, f"No data for subject {subject} in period {study_period}.")
        used_period = study_period
    else:
        used_period = str(df_subj["STUDYPERIOD"].dropna().max())
        df_period = df_subj[df_subj["STUDYPERIOD"] == used_period]
    types_df = (
        df_period
        .drop_duplicates(subset=["ASSESSMENTTYPECODE"])
        [["ASSESSMENTTYPECODE", "WEIGHTING"]]
        .sort_values("WEIGHTING", ascending=False)
    )
    assessment_list = [
        {"assessmentType": str(r["ASSESSMENTTYPECODE"]), "weighting": float(r["WEIGHTING"])}
        for _, r in types_df.iterrows()
        if float(r["WEIGHTING"]) > 0
    ]
    total_weight = sum(a["weighting"] for a in assessment_list)
    response = {
        "subject":         subject,
        "study_period":    used_period,
        "assessments":     assessment_list,
        "total_weight":    total_weight,
        "weight_complete": total_weight == 100.0,
    }
    if reliability == "mostly_clean":
        response["reliability_warning"] = (
            "This subject's data was only partially verified during cleaning — "
            "assessment weightings may be incomplete."
        )
    return response


@app.get("/api/subjects/{subject}/roster", tags=["Subjects"])
async def subject_roster(
    subject:           str,
    study_period:      str             = Query(...),
    simulate_progress: Optional[float] = Query(None, ge=0, le=100),
    user:              dict            = Depends(get_current_user),
    db:                AsyncSession    = Depends(get_db),
):
    """Return one row per student for a subject+period: progress, weighted score, and risk band.

    simulate_progress is a dev/demo-only override — Capstone_data_20260729.csv is a
    closed, term-end dataset where every student already has 100% weighting recorded,
    so there's no real mid-semester partial-progress data to test against. When set,
    each student's real items are truncated to a simulated submission-order prefix
    before the same feature/prediction logic below runs. Not meaningful once a live
    feed exists — remove this param at that point.
    """
    from app.ml.predictor import (
        predict as ml_predict,
        predict_partial as ml_predict_partial,
        classify_coverage,
    )

    if _DATA is None or _DATA.empty:
        raise HTTPException(503, "No data loaded. Upload a dataset first.")

    is_admin  = user.get("role") in {"Head of Technology", "Head of School"}
    subj_list = user.get("subjects", [])
    if not is_admin and subject not in subj_list:
        raise HTTPException(403, "You are not assigned to that subject.")

    df_subj = _DATA[_DATA["SUBJECTCODE"] == subject]
    if df_subj.empty:
        raise HTTPException(404, "Subject not found.")

    # Always derive from subject_reliability.json directly — see the /api/predict
    # comment above for why _SAFE_SUBJECTS membership isn't a valid shortcut here.
    reliability = _subject_reliability_category(subject)
    if reliability == "unreliable":
        return {
            "subject":              subject,
            "prediction_available": False,
            "message": (
                "Prediction unavailable for this subject due to incomplete "
                "assessment data. Contact your Head of Technology."
            ),
        }

    df_period = df_subj[df_subj["STUDYPERIOD"] == study_period]
    if df_period.empty:
        raise HTTPException(404, f"No data for subject {subject} in period {study_period}.")
    df_period = df_period.dropna(subset=["MARKPERCENT"])

    # Shared with /api/predict so both endpoints derive the same coverage
    # fraction — and therefore the same mid-term attendance truncation — for
    # the same enrolment.
    period_total_weight = _period_total_weight(subject, study_period)
    trimester_num = float(study_period)

    roster = []
    for student_id, grp in df_period.groupby("STUDENTID_MASKED"):
        if simulate_progress is not None:
            grp_seq      = grp.sort_values("STUDYPACKAGEASSESSMENTID").reset_index(drop=True)
            cum_seq      = grp_seq["WEIGHTING"].cumsum()
            grp_included = grp_seq[cum_seq <= simulate_progress]
            if grp_included.empty:
                continue
            grp_sorted = grp_included.sort_values("WEIGHTING", ascending=False).reset_index(drop=True)
        else:
            grp_sorted = grp.sort_values("WEIGHTING", ascending=False).reset_index(drop=True)
        n_recorded             = len(grp_sorted)
        cumulative_weighting   = float(grp_sorted["WEIGHTING"].sum())
        current_weighted_score = float((grp_sorted["MARKPERCENT"] * grp_sorted["WEIGHTING"] / 100).sum())

        assessments_used = [
            {
                "type":         str(r["ASSESSMENTTYPECODE"]),
                "mark_percent": float(r["MARKPERCENT"]),
                "weighting":    float(r["WEIGHTING"]),
            }
            for _, r in grp_sorted.iterrows()
        ]

        coverage_tier = classify_coverage(cumulative_weighting)

        if coverage_tier == "insufficient":
            # Coverage gate, not a data-quality gate — no model call, this
            # student just sorts last (probability is None) same as an
            # unscored student already does below.
            row = {
                "student_id":                    str(student_id),
                "num_assessments_recorded":      n_recorded,
                "cumulative_weighting_recorded": round(cumulative_weighting, 1),
                "current_weighted_score":        round(current_weighted_score, 1),
                "probability":                   None,
                "prediction":                    None,
                "risk_band":                     None,
                "coverage_status":               "insufficient_data",
            }
            roster.append(row)
            continue

        if coverage_tier == "complete":
            # ── UNCHANGED — existing top-2, best_model.pkl path. Do not touch. ──
            a1         = grp_sorted.iloc[0]
            a1_mark    = float(a1["MARKPERCENT"])
            a1_weight  = float(a1["WEIGHTING"])
            a1_contrib = a1_mark * a1_weight / 100

            if n_recorded > 1:
                a2        = grp_sorted.iloc[1]
                a2_mark   = float(a2["MARKPERCENT"])
                a2_weight = float(a2["WEIGHTING"])
            else:
                a2_mark   = 0.0
                a2_weight = 0.0
            a2_contrib = a2_mark * a2_weight / 100

            # This student's real, full attendance rate — safe for a complete
            # record (same closed-snapshot premise build_early_features()
            # relies on). Resolved through the same shared function
            # /api/predict uses, so the two endpoints cannot disagree about
            # the same student again.
            attendance_rate, _ = _resolve_attendance_rate(
                str(student_id), subject, study_period
            )

            result = ml_predict(
                subject=                 subject,
                study_period=            study_period,
                trimester_num=           trimester_num,
                assess1_mark=            a1_mark,
                assess1_weight=          a1_weight,
                assess1_contribution=    a1_contrib,
                assess2_mark=            a2_mark,
                assess2_weight=          a2_weight,
                assess2_contribution=    a2_contrib,
                partial_weighted_score=  a1_contrib + a2_contrib,
                partial_weight_coverage= (a1_weight + a2_weight) / 100,
                num_assessments=         n_recorded,
                total_weight_recorded=   cumulative_weighting,
                weight_complete=         cumulative_weighting >= period_total_weight,
                assessments_used=        assessments_used,
                attendance_rate=         attendance_rate,
            )
            estimate_type = None
        else:  # "partial" — 50-99% coverage, genuinely mid-term
            # Attendance truncated to the SAME coverage fraction this
            # student's marks have reached — never the full/final rate,
            # which would leak end-of-term information into a mid-term
            # estimate (see _truncated_attendance_rate's docstring).
            coverage_fraction = cumulative_weighting / period_total_weight if period_total_weight else 0.0
            attendance_rate, _ = _resolve_attendance_rate(
                str(student_id), subject, study_period, coverage_fraction
            )

            result = ml_predict_partial(
                subject=          subject,
                study_period=     study_period,
                trimester_num=    trimester_num,
                assessments_used= assessments_used,
                attendance_rate=  attendance_rate,
            )
            estimate_type = "mid-term estimate"

        row = {
            "student_id":                    str(student_id),
            "num_assessments_recorded":      n_recorded,
            "cumulative_weighting_recorded": round(cumulative_weighting, 1),
            "current_weighted_score":        round(current_weighted_score, 1),
            "probability":                   result.get("probability"),
            "prediction":                    result.get("prediction"),
            "risk_band":                     result.get("risk_band"),
            "estimate_type":                 estimate_type,
            # Derived from this row's own real SHAP explanation. The full
            # explanation is intentionally NOT included in a roster row (it is
            # ~11 factors per student, so a 39-student roster would carry
            # hundreds of objects the table never renders) — only the single
            # actionable conclusion, which is what the roster can act on.
            "top_actionable_factor":         top_actionable_factor(result.get("shap_explanation")),
            # Why this row has no probability, when it has none. The roster
            # folds a model error into probability=None, which is exactly how a
            # real outage once hid behind HTTP 200 (see README, Testing
            # Practices). A missing required feature — e.g. a subject with no
            # attendance data — must be visible as a stated reason rather than
            # an unexplained blank cell.
            "data_status": (
                "missing_required_data"
                if str(result.get("error", "")).startswith("missing_required_feature")
                else None
            ),
            # Additive — surfaces the attendance rate this row was actually
            # scored with, so the roster and /api/predict can be checked
            # against each other for the same student (see
            # test_predict_and_roster_agree_on_a_real_students_attendance).
            "attendance_rate_used":          result.get("attendance_rate_used"),
        }
        roster.append(row)

        # simulate_progress is a dev/demo-only override (see this endpoint's
        # docstring) — never persist a prediction derived from fabricated
        # truncated data as if it were a real one to later reconcile.
        # commit=False: batched into one commit after the loop rather than a
        # round-trip per student — this loop can run 250+ times per call.
        if simulate_progress is None:
            await _upsert_prediction(
                db,
                student_id_masked = str(student_id),
                subject_code       = subject,
                study_period        = study_period,
                result              = result,
                commit              = False,
            )

    if simulate_progress is None and roster:
        await db.commit()

    # Highest risk first — lowest pass-probability first; unscored students (model
    # unavailable) sort last rather than being mixed in among ranked students.
    roster.sort(key=lambda r: (r["probability"] is None, r["probability"] if r["probability"] is not None else 0))

    response = {
        "subject":             subject,
        "study_period":        study_period,
        "total_students":      len(roster),
        "period_total_weight": float(period_total_weight),
        "simulated":           simulate_progress is not None,
        "roster":              roster,
    }
    if reliability == "mostly_clean":
        response["reliability_warning"] = (
            "This subject's data was only partially verified during cleaning — "
            "assessment weightings may be incomplete."
        )
    return response


@app.get("/api/students-at-risk", tags=["Subjects"])
async def students_at_risk(
    study_period: str          = Query(...),
    user:         dict         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """
    Cross-subject risk view for one study period — one row per (student,
    subject) enrolment, aggregated across every subject the requesting user
    can see (every subject for an admin/Head of School, only their assigned
    subjects for a lecturer — same visibility rule subject_roster() already
    enforces per call).

    Deliberately reuses subject_roster() per subject rather than re-deriving
    the same coverage/prediction logic here: same risk_band values, same
    SAFE_SUBJECTS/reliability gating, same guarantee this can never disagree
    with what /api/subjects/{subject}/roster shows for the same student.
    """
    if _DATA is None or _DATA.empty:
        raise HTTPException(503, "No data loaded. Upload a dataset first.")

    is_admin = user.get("role") in {"Head of Technology", "Head of School"}
    subjects = (
        sorted(_DATA["SUBJECTCODE"].dropna().unique().tolist()) if is_admin
        else list(user.get("subjects", []))
    )

    combined: list = []
    subjects_included = 0
    for subj in subjects:
        try:
            result = await subject_roster(
                subject=subj, study_period=study_period, simulate_progress=None,
                user=user, db=db,
            )
        except HTTPException:
            # No data for this subject in this period, or the subject code
            # doesn't exist in _DATA at all — just not part of this period's
            # picture, not an error for the whole aggregate view.
            continue
        if not result.get("prediction_available", True):
            continue  # unreliable subject — subject_roster already declines to score it
        if result.get("roster"):
            subjects_included += 1
        for row in result["roster"]:
            combined.append({**row, "subject": subj})

    combined.sort(key=lambda r: (r["probability"] is None, r["probability"] if r["probability"] is not None else 0))

    return {
        "study_period":      study_period,
        "subjects_included": subjects_included,
        "total_rows":        len(combined),
        "students":          combined,
    }


@app.get("/api/subjects/analytics", tags=["Subjects"])
async def subjects_analytics(
    subject_a: str           = Query(...),
    subject_b: Optional[str] = Query(None),
    trimester: Optional[str] = Query(None),
    user: dict = Depends(require_head_of_school),
):
    """Return analytics for one or two subjects for side-by-side comparison."""
    stats_a = _calc_subject_analytics(subject_a, trimester)
    if not stats_a:
        raise HTTPException(404, f"No data found for subject {subject_a}")
    stats_b = _calc_subject_analytics(subject_b, trimester) if subject_b else None
    return {"subject_a": stats_a, "subject_b": stats_b}

# ─────────────────────────────────────────────────────────────────────────────
# Admin Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/audit-logs", tags=["Audit"])
async def get_audit_logs(
    action_type:   Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None),
    user: dict = Depends(require_admin),
    db:   AsyncSession = Depends(get_db),
):
    """Return all audit log entries, optionally filtered by action type or status."""
    await _append_audit_db(db, user_uid=user["sub"], action_type="Data Access",
                           status="Success", detail="Viewed audit log")
    query = select(AuditLog).order_by(desc(AuditLog.id))
    if action_type:
        query = query.where(AuditLog.action_type == action_type)
    if status_filter:
        query = query.where(AuditLog.status == status_filter)
    result = await db.execute(query)
    logs   = result.scalars().all()

    # Resolve each user_uid to its current role in one batch query so the
    # frontend never has to infer role from UID patterns (which fails for
    # real email addresses like principal@koi.edu.au).
    uids = {log.user_uid for log in logs}
    role_rows = await db.execute(
        select(UserModel.email, UserModel.role).where(UserModel.email.in_(uids))
    )
    role_map: dict[str, str] = dict(role_rows.all())

    data = [
        {
            "event_id":    log.id,
            "timestamp":   log.timestamp.strftime("%Y-%m-%d %H:%M") if log.timestamp else "",
            "user_uid":    log.user_uid,
            "role":        role_map.get(log.user_uid),
            "action_type": log.action_type,
            "status":      log.status,
            "detail":      log.detail,
        }
        for log in logs
    ]
    return {"total": len(data), "count": len(data), "data": data}


@app.get("/api/users", tags=["Admin"])
async def list_users(
    user: dict = Depends(require_super_admin),
    db:   AsyncSession = Depends(get_db),
):
    """Return all non-admin user accounts."""
    result = await db.execute(select(UserModel).where(UserModel.email != "admin"))
    users  = result.scalars().all()
    return [
        {
            "email":    u.email,
            "name":     u.name,
            "role":     u.role,
            "subjects": u.subjects or [],
            "active":   u.is_active,
        }
        for u in users
    ]


@app.post("/api/users", status_code=201, tags=["Admin"])
async def create_user(
    payload: CreateUserRequest,
    user: dict = Depends(require_super_admin),
    db:   AsyncSession = Depends(get_db),
):
    """Create a new staff account with role and subject assignments."""
    domain = payload.email.split('@')[1]
    if '.' not in domain:
        raise HTTPException(400, "Please enter a valid institutional email address.")
    if not payload.name.strip():
        raise HTTPException(400, "Name must not be empty.")
    _validate_password(payload.password)
    if payload.role not in {"Lecturer", "Head of Technology", "Head of School"}:
        raise HTTPException(400, "Role must be 'Lecturer', 'Head of Technology', or 'Head of School'.")
    if payload.role == "Lecturer" and not payload.subjects:
        raise HTTPException(400, "At least one subject must be assigned for a Lecturer.")

    existing = await db.execute(select(UserModel).where(UserModel.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Email already exists.")

    subjects = [] if payload.role in {"Head of Technology", "Head of School"} else payload.subjects
    new_user = UserModel(
        email=payload.email,
        name=payload.name.strip(),
        hashed_password=_pwd.hash(payload.password),
        role=payload.role,
        is_active=True,
        subjects=subjects,
    )
    db.add(new_user)
    await db.flush()  # get the id without committing yet

    detail = (
        f"{payload.role} account created: {payload.email}"
        + (f" assigned to {', '.join(subjects)}" if subjects else "")
    )
    await _append_audit_db(db, user_uid=user["sub"], action_type="User Created",
                           status="Success", detail=detail)
    return {
        "message": f"{payload.role} account created",
        "user":    {"email": payload.email, "name": payload.name,
                    "role": payload.role,   "subjects": subjects},
    }


@app.put("/api/users/{email}", tags=["Admin"])
async def update_user(
    email:   str,
    payload: UpdateUserRequest,
    user: dict = Depends(require_super_admin),
    db:   AsyncSession = Depends(get_db),
):
    """Update subject assignments or active status for an existing account."""
    result  = await db.execute(select(UserModel).where(UserModel.email == email))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(404, "User not found.")
    if db_user.email == "admin":
        raise HTTPException(403, "Cannot modify the system administrator account.")

    if payload.subjects is not None:
        db_user.subjects = payload.subjects
    if payload.active is not None:
        db_user.is_active = payload.active
        status_str = "activated" if payload.active else "deactivated"
        await _append_audit_db(db, user_uid=user["sub"], action_type="User Modified",
                               status="Success", detail=f"Account {status_str}: {email}")
    else:
        await _append_audit_db(db, user_uid=user["sub"], action_type="User Modified",
                               status="Success", detail=f"Account updated: {email}")
    return {"message": "Account updated"}


@app.delete("/api/users/{email}", tags=["Admin"])
async def delete_user(
    email: str,
    user: dict = Depends(require_super_admin),
    db:   AsyncSession = Depends(get_db),
):
    """Permanently delete a staff account; prevents self-deletion and admin removal."""
    result  = await db.execute(select(UserModel).where(UserModel.email == email))
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(404, "User not found.")
    if db_user.email == "admin":
        raise HTTPException(403, "Cannot delete the system administrator account.")
    if email == user.get("sub"):
        raise HTTPException(403, "Cannot delete your own account.")

    await db.delete(db_user)
    await _append_audit_db(db, user_uid=user["sub"], action_type="User Modified",
                           status="Success", detail=f"Account deleted: {email}")
    return {"message": "Account deleted"}


# ═══════════════════════════════════════════════════════════════════════════
# API Console — admin-issued keys for the external /api/v1/predict endpoint
# ═══════════════════════════════════════════════════════════════════════════
# Gated by require_admin (any Head of Technology), not require_super_admin —
# this is a role-based feature like /api/audit-logs, not restricted to the
# single literal "admin" account the way /api/users is.

@app.get("/api/api-keys", tags=["Admin"])
async def list_api_keys(
    user: dict = Depends(require_admin),
    db:   AsyncSession = Depends(get_db),
):
    """List API keys, newest first. Never returns the raw key or its hash."""
    result = await db.execute(select(ApiKey).order_by(desc(ApiKey.created_at)))
    keys = result.scalars().all()
    return [
        {
            "id":            k.id,
            "name":          k.name,
            "key_prefix":    k.key_prefix,
            "created_by":    k.created_by,
            "created_at":    k.created_at,
            "last_used_at":  k.last_used_at,
            "revoked":       k.revoked,
        }
        for k in keys
    ]


@app.post("/api/api-keys", status_code=201, tags=["Admin"])
async def create_api_key(
    payload: CreateApiKeyRequest,
    user: dict = Depends(require_admin),
    db:   AsyncSession = Depends(get_db),
):
    """Generate a new API key. The raw key is returned only in this response
    — it is never recoverable again, only re-issuable via a new key."""
    raw_key    = "edapt_" + secrets.token_urlsafe(32)
    key_hash   = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:14]

    new_key = ApiKey(
        name=payload.name.strip(),
        key_prefix=key_prefix,
        hashed_key=key_hash,
        created_by=user["sub"],
    )
    db.add(new_key)
    await db.flush()

    await _append_audit_db(db, user_uid=user["sub"], action_type="API Key Created",
                           status="Success", detail=f"API key created: {payload.name.strip()}")

    return {
        "id":         new_key.id,
        "name":       new_key.name,
        "api_key":    raw_key,
        "key_prefix": new_key.key_prefix,
        "created_at": new_key.created_at,
    }


@app.delete("/api/api-keys/{key_id}", tags=["Admin"])
async def revoke_api_key(
    key_id: int,
    user: dict = Depends(require_admin),
    db:   AsyncSession = Depends(get_db),
):
    """Soft-revoke an API key — kept for audit history, never hard-deleted."""
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(404, "API key not found.")
    if key.revoked:
        raise HTTPException(400, "This API key is already revoked.")

    key.revoked = True
    key.revoked_at = datetime.now(timezone.utc)
    await _append_audit_db(db, user_uid=user["sub"], action_type="API Key Revoked",
                           status="Success", detail=f"API key revoked: {key.name}")
    return {"message": "API key revoked"}


@app.get("/api/api-keys/usage", tags=["Admin"])
async def api_key_usage(
    days: int = Query(30, ge=1, le=90),
    user: dict = Depends(require_admin),
    db:   AsyncSession = Depends(get_db),
):
    """Daily /api/v1/predict request-volume history for the API Console usage
    chart. Built from the existing audit log rather than a new table — every
    successful external prediction already writes an "External API Prediction"
    row there (see predict_via_api_key), so this just aggregates what's already
    recorded rather than tracking usage twice."""
    cutoff_day = (datetime.now(timezone.utc) - timedelta(days=days - 1)).date()
    result = await db.execute(
        select(AuditLog.timestamp, AuditLog.user_uid)
        .where(AuditLog.action_type == "External API Prediction")
        .where(AuditLog.timestamp >= cutoff_day)
    )
    rows = result.all()

    day_list  = [(cutoff_day + timedelta(days=i)).isoformat() for i in range(days)]
    day_index = {d: i for i, d in enumerate(day_list)}

    total_counts = [0] * days
    per_key_counts: dict[str, list[int]] = {}
    for ts, uid in rows:
        idx = day_index.get(ts.date().isoformat())
        if idx is None:
            continue
        total_counts[idx] += 1
        key_name = uid[len("api-key:"):] if uid.startswith("api-key:") else uid
        per_key_counts.setdefault(key_name, [0] * days)[idx] += 1

    # Cap at the busiest 4 keys, matching the chart's 4-slot categorical
    # palette — any remainder folds into "Other" rather than growing an
    # unbounded number of series (see dataviz skill's categorical-palette rule).
    ranked    = sorted(per_key_counts.items(), key=lambda kv: sum(kv[1]), reverse=True)
    top, rest = ranked[:4], ranked[4:]
    by_key = [{"name": name, "counts": counts} for name, counts in top]
    if rest:
        other_counts = [0] * days
        for _, counts in rest:
            for i, c in enumerate(counts):
                other_counts[i] += c
        by_key.append({"name": "Other", "counts": other_counts})

    return {"days": day_list, "total": total_counts, "by_key": by_key}


@app.post("/api/v1/predict", tags=["Public API"])
async def predict_via_api_key(
    req:     ApiPredictRequest,
    key_row: ApiKey = Depends(require_api_key),
    db:      AsyncSession = Depends(get_db),
):
    """External pass/fail prediction endpoint, authenticated by X-API-Key
    instead of a session JWT. Mirrors /api/predict's coverage-gating and
    safety behaviour exactly, but derives assess1/assess2 itself (via
    predictor._top2_by_weight) rather than trusting a client-supplied top-2,
    since an external caller has no reason to know that internal convention.
    """
    from app.ml.predictor import (
        predict as ml_predict,
        predict_partial as ml_predict_partial,
        compute_partial_score,
        classify_coverage,
        _top2_by_weight,
    )

    reliability = _subject_reliability_category(req.subject)
    if reliability == "unreliable":
        return {
            "prediction_available": False,
            "message": (
                "Prediction unavailable for this subject due to incomplete "
                "assessment data. Contact your Head of Technology."
            ),
        }

    assessments = [a.model_dump() for a in req.assessments]
    cumulative_weighting = sum(a["weighting"] for a in assessments)
    coverage_tier = classify_coverage(cumulative_weighting)

    if coverage_tier == "insufficient":
        return {
            "prediction_available": False,
            "coverage_status":      "insufficient_data",
            "message": (
                f"Not enough assessment data recorded yet to generate a prediction "
                f"({cumulative_weighting:.0f}% of the term recorded)."
            ),
        }

    attendance_rate = req.attendance_percentage / 100

    if coverage_tier == "complete":
        partial_weighted_score, partial_weight_coverage = compute_partial_score(assessments)
        a1_mark, a1_weight, a1_contrib, a2_mark, a2_weight, a2_contrib = _top2_by_weight(assessments)
        result = ml_predict(
            subject=                 req.subject,
            study_period=            req.study_period,
            trimester_num=           req.trimester_num,
            assess1_mark=            a1_mark,
            assess1_weight=          a1_weight,
            assess1_contribution=    a1_contrib,
            assess2_mark=            a2_mark,
            assess2_weight=          a2_weight,
            assess2_contribution=    a2_contrib,
            partial_weighted_score=  partial_weighted_score,
            partial_weight_coverage= partial_weight_coverage,
            num_assessments=         len(assessments),
            total_weight_recorded=   cumulative_weighting,
            weight_complete=         True,
            assessments_used=        assessments,
            attendance_rate=         attendance_rate,
        )
    else:  # "partial" — 50-99% coverage, genuinely mid-term
        result = ml_predict_partial(
            subject=          req.subject,
            study_period=     req.study_period,
            trimester_num=    req.trimester_num,
            assessments_used= assessments,
            attendance_rate=  attendance_rate,
        )

    if "error" in result:
        error_text = str(result["error"])
        if error_text.startswith("missing_required_feature"):
            missing_feature = error_text.split(":", 1)[1].split(" is required")[0].strip()
            return {
                "prediction_available": False,
                "data_status":          "missing_required_data",
                "missing_feature":      missing_feature,
                "message": (
                    f"Not enough data to generate a prediction: this subject has no "
                    f"{missing_feature.replace('_', ' ').lower()} recorded, which the "
                    f"current model requires."
                ),
            }
        raise HTTPException(503, "ML model is not loaded. Run train_model.py first.")

    await _append_audit_db(db, user_uid=f"api-key:{key_row.name}", action_type="External API Prediction",
                           status="Success",
                           detail=f"Predicted {req.subject}: {result['probability']}% pass probability")

    return {
        "prediction_available": True,
        "subject":              req.subject,
        "study_period":         req.study_period,
        "coverage_status":      coverage_tier,
        "result":               result["prediction"],
        "pass_percentage":      result["probability"],
        "risk_band":            result["risk_band"],
        "estimate_type":        result.get("estimate_type"),
        "model_version":        result["model_version"],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Interventions — real actions a human took for a student
# ═══════════════════════════════════════════════════════════════════════════
# A prediction says who is at risk; this records what anyone actually DID
# about it. Kept deliberately separate from the prediction itself — see the
# Intervention model's docstring for why it is its own table.

# App-level whitelist rather than a DB enum, so adding a type is a one-line
# change in a project with no migration framework. "other" is included so a
# real action that doesn't fit the list is still recorded rather than lost —
# the free-text note carries the detail.
INTERVENTION_ACTION_TYPES = [
    "email sent",
    "meeting scheduled",
    "referred to support services",
    "other",
]


class InterventionCreate(BaseModel):
    student_id_masked: str = Field(..., min_length=1, max_length=50)
    subject_code:      str = Field(..., min_length=1, max_length=20)
    study_period:      str = Field(..., min_length=1, max_length=10)
    action_type:       str = Field(..., min_length=1, max_length=50)
    notes:   Optional[str] = Field(None, max_length=2000)
    prediction_id: Optional[int] = None


def _assert_subject_visible(subject: str, user: dict) -> None:
    """SQL-side equivalent of _role_filter (which only works on DataFrames).

    A Lecturer may only touch interventions for subjects they are assigned;
    Head of Technology / Head of School see everything, matching how every
    other lecturer-facing endpoint in this file scopes.
    """
    if user.get("role") == "Lecturer" and subject not in (user.get("subjects") or []):
        raise HTTPException(403, "You are not assigned to that subject.")


@app.post("/api/interventions", status_code=201, tags=["Interventions"])
async def create_intervention(
    req:  InterventionCreate,
    user: dict         = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """Log a real action taken for a student."""
    if req.action_type not in INTERVENTION_ACTION_TYPES:
        raise HTTPException(
            422,
            f"action_type must be one of: {', '.join(INTERVENTION_ACTION_TYPES)}",
        )
    _assert_subject_visible(req.subject_code, user)

    # Validate the FK rather than letting the database raise: a bad
    # prediction_id should be a clear 422, not a 500 from an integrity error.
    if req.prediction_id is not None:
        exists = await db.execute(
            select(Prediction.id).where(Prediction.id == req.prediction_id)
        )
        if exists.scalar_one_or_none() is None:
            raise HTTPException(422, f"No prediction with id {req.prediction_id}.")

    row = Intervention(
        student_id_masked = req.student_id_masked,
        subject_code      = req.subject_code,
        study_period      = req.study_period,
        action_type       = req.action_type,
        notes             = req.notes,
        prediction_id     = req.prediction_id,
        created_by        = user["sub"],
    )
    db.add(row)
    await db.flush()          # populate row.id before the session closes
    new_id = row.id

    await _append_audit_db(
        db, user_uid=user["sub"], action_type="Intervention Logged", status="Success",
        detail=f"{req.action_type} for {req.student_id_masked} in {req.subject_code} ({req.study_period})",
    )
    return {
        "id":                new_id,
        "student_id_masked": row.student_id_masked,
        "subject_code":      row.subject_code,
        "study_period":      row.study_period,
        "action_type":       row.action_type,
        "notes":             row.notes,
        "prediction_id":     row.prediction_id,
        "created_by":        row.created_by,
    }


@app.get("/api/interventions", tags=["Interventions"])
async def list_interventions(
    student_id_masked: Optional[str] = Query(None, max_length=50),
    subject_code:      Optional[str] = Query(None, max_length=20),
    study_period:      Optional[str] = Query(None, max_length=10),
    limit:             int           = Query(200, ge=1, le=1000),
    user:              dict          = Depends(get_current_user),
    db:                AsyncSession  = Depends(get_db),
):
    """List logged interventions, newest first.

    Scoping is applied to the QUERY, not to the response after the fact, so a
    lecturer's rows for other subjects are never loaded at all. A Lecturer with
    no assigned subjects sees nothing rather than everything — the failure mode
    here should be empty, not open.
    """
    query = select(Intervention)

    if user.get("role") == "Lecturer":
        allowed = user.get("subjects") or []
        if not allowed:
            return {"interventions": [], "count": 0}
        query = query.where(Intervention.subject_code.in_(allowed))

    if student_id_masked:
        query = query.where(Intervention.student_id_masked == student_id_masked)
    if subject_code:
        _assert_subject_visible(subject_code, user)
        query = query.where(Intervention.subject_code == subject_code)
    if study_period:
        query = query.where(Intervention.study_period == study_period)

    query = query.order_by(desc(Intervention.created_at), desc(Intervention.id)).limit(limit)
    rows = (await db.execute(query)).scalars().all()

    return {
        "count": len(rows),
        "interventions": [
            {
                "id":                r.id,
                "student_id_masked": r.student_id_masked,
                "subject_code":      r.subject_code,
                "study_period":      r.study_period,
                "action_type":       r.action_type,
                "notes":             r.notes,
                "prediction_id":     r.prediction_id,
                "created_by":        r.created_by,
                "created_at":        r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@app.get("/api/interventions/action-types", tags=["Interventions"])
async def intervention_action_types(user: dict = Depends(get_current_user)):
    """The whitelist the UI renders, so the frontend never hardcodes its own
    copy and drift between the two is impossible."""
    return {"action_types": INTERVENTION_ACTION_TYPES}


class InterventionBulkTarget(BaseModel):
    student_id_masked: str = Field(..., min_length=1, max_length=50)
    subject_code:      str = Field(..., min_length=1, max_length=20)
    study_period:      str = Field(..., min_length=1, max_length=10)
    risk_band:  Optional[str] = Field(None, max_length=20)


class InterventionBulkCreate(BaseModel):
    targets:     list[InterventionBulkTarget] = Field(..., min_length=1, max_length=500)
    action_type: str           = Field(..., min_length=1, max_length=50)
    notes:       Optional[str] = Field(None, max_length=2000)


def _render_risk_email(template: str, target: "InterventionBulkTarget") -> str:
    return (
        template
        .replace("{{student_id}}",   target.student_id_masked)
        .replace("{{subject_code}}", target.subject_code)
        .replace("{{study_period}}", target.study_period)
        .replace("{{risk_band}}",    target.risk_band or "at risk")
    )


@app.post("/api/interventions/bulk", status_code=201, tags=["Interventions"])
async def create_interventions_bulk(
    req:  InterventionBulkCreate,
    user: dict         = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """
    Log the same action for many students at once — built for the Students
    at Risk page's bulk "mark as emailed" action. This never sends a real
    email (see RiskEmailTemplate's docstring for why: no real student email
    exists anywhere in this system) — it only records, per selected
    student, that a staff member already did that themselves.

    req.notes, if given, is treated as a template and rendered per-target
    (see _render_risk_email) so each Intervention row's notes reflects that
    specific student/subject/period rather than one identical blob of text
    with unresolved {{placeholders}} across every row.
    """
    if req.action_type not in INTERVENTION_ACTION_TYPES:
        raise HTTPException(
            422,
            f"action_type must be one of: {', '.join(INTERVENTION_ACTION_TYPES)}",
        )
    for t in req.targets:
        _assert_subject_visible(t.subject_code, user)

    created_ids = []
    for t in req.targets:
        row = Intervention(
            student_id_masked = t.student_id_masked,
            subject_code       = t.subject_code,
            study_period        = t.study_period,
            action_type          = req.action_type,
            notes                = _render_risk_email(req.notes, t) if req.notes else None,
            created_by           = user["sub"],
        )
        db.add(row)
        await db.flush()
        created_ids.append(row.id)

    await _append_audit_db(
        db, user_uid=user["sub"], action_type="Intervention Logged", status="Success",
        detail=f"Bulk-logged '{req.action_type}' for {len(created_ids)} student(s)",
    )
    return {"created": len(created_ids), "ids": created_ids}


class RiskEmailTemplateUpdate(BaseModel):
    subject: str = Field(..., min_length=1, max_length=255)
    body:    str = Field(..., min_length=1, max_length=5000)


@app.get("/api/risk-email-template", tags=["Interventions"])
async def get_risk_email_template(
    user: dict         = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    """The current Students-at-Risk bulk-email template — readable by any
    authenticated role so the Students at Risk page can render a preview."""
    row = await db.get(RiskEmailTemplate, 1)
    return {
        "subject":     row.subject,
        "body":        row.body,
        "updated_by":  row.updated_by,
        "updated_at":  row.updated_at.isoformat() if row.updated_at else None,
    }


@app.put("/api/risk-email-template", tags=["Interventions"])
async def update_risk_email_template(
    req:  RiskEmailTemplateUpdate,
    user: dict         = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """Update the shared template — admin-only (Head of Technology / Head of
    School), matching how other institution-wide config is gated in this app."""
    row = await db.get(RiskEmailTemplate, 1)
    now = datetime.now(timezone.utc)
    row.subject    = req.subject
    row.body       = req.body
    row.updated_by = user["sub"]
    row.updated_at = now

    # _append_audit_db commits, which expires every attribute on `row` —
    # reading req.subject/user["sub"]/now (already-known values, not a
    # re-read of the now-expired ORM object) avoids the async lazy-load
    # that a post-commit `row.x` access would otherwise trigger outside a
    # valid greenlet context (a real, confirmed MissingGreenlet crash here,
    # not a hypothetical one).
    await _append_audit_db(
        db, user_uid=user["sub"], action_type="Settings Changed", status="Success",
        detail="Updated the Students-at-Risk email template",
    )
    return {
        "subject":     req.subject,
        "body":        req.body,
        "updated_by":  user["sub"],
        "updated_at":  now.isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Model health — admin-only, READ-ONLY
# ═══════════════════════════════════════════════════════════════════════════
# DESIGN DECISION, DELIBERATE: this endpoint exposes no promote, rollback, or
# retrain action, and the dashboard built on it has no such controls. Model
# promotion stays a considered CLI action behind the existing >3pp gate
# (compare_and_promote.py / compare_and_promote_simulated.py), which forces a
# human to read a comparison and, for a borderline case, type --force with a
# recorded justification. A one-click "Promote" button in a web UI would route
# around the exact safeguard this project built after a model went live
# ungated with no recoverable backup. Read-only is the feature.
#
# Every number here comes from the real registries and the real scripts —
# nothing is recomputed locally, so the dashboard cannot disagree with what
# the CLI reports.

def _live_model_summary() -> dict:
    """Current live model of each family, straight from its registry file."""
    from app.ml.model_registry import load_registry as load_main_registry, get_live_entry as live_main
    from app.ml.sim_model_registry import load_registry as load_sim_registry, get_live_entry as live_sim
    from app.ml import predictor
    # The complete-record threshold is a module constant; the mid-term one is
    # stored per-model in the package because it is re-selected on every
    # retrain, so it is read from the loaded package rather than from a
    # constant that would go stale the moment a mid-term model is promoted.
    FAIL_THRESHOLD = predictor.FAIL_THRESHOLD
    SIM_FAIL_THRESHOLD = (
        predictor._SIM_PACKAGE.get("decision_threshold") if predictor._SIM_PACKAGE else None
    )

    def summarise(entry, registry, serving_threshold, served_features, family):
        if not entry:
            return {"family": family, "live": False,
                    "error": "no live version registered for this family"}

        # The two registries genuinely have different entry shapes (the
        # complete-record one predates the mid-term one and stores no
        # `features` list), so read defensively rather than assume a schema.
        report = entry.get("classification_report") or {}
        fail = report.get("Fail") or {}

        # promoted_at lives in the registry-level promotion_history, not on the
        # version entry. Take the most recent promotion OF THIS VERSION.
        promoted_at = None
        for record in reversed(registry.get("promotion_history", []) or []):
            if record.get("version") == entry.get("version"):
                promoted_at = record.get("promoted_at")
                break

        # Registry entries record the threshold VALIDATED at training time.
        # What actually serves traffic is the value predictor uses right now.
        # They can legitimately differ (the complete-record sweep suggested
        # 0.475, inside the project's noise band, so 0.50 stayed deployed), and
        # collapsing them into one number would hide that.
        registered_threshold = entry.get("decision_threshold")
        features = entry.get("features") or served_features or []

        return {
            "family":            family,
            "live":              True,
            "version":           entry.get("version"),
            "trained_on":        entry.get("trained_on"),
            "validated_on":      entry.get("validated_on"),
            "trained_at":        entry.get("trained_at"),
            "promoted_at":       promoted_at,
            "train_row_count":   entry.get("train_row_count"),
            "n_features":        len(features),
            "features":          features,
            "features_source":   "registry entry" if entry.get("features") else "loaded model package",
            "decision_threshold_serving":    serving_threshold,
            "decision_threshold_registered": registered_threshold,
            "threshold_matches_registry":    serving_threshold == registered_threshold,
            "metrics": {
                "accuracy":       entry.get("accuracy"),
                "fail_precision": fail.get("precision"),
                "fail_recall":    fail.get("recall"),
                "fail_f1":        fail.get("f1-score"),
                "fail_support":   fail.get("support"),
            },
        }

    main_reg, sim_reg = load_main_registry(), load_sim_registry()
    return {
        "complete_record": summarise(
            live_main(main_reg), main_reg, FAIL_THRESHOLD,
            (predictor._PACKAGE or {}).get("features"), "complete-record"),
        "mid_term": summarise(
            live_sim(sim_reg), sim_reg, SIM_FAIL_THRESHOLD,
            (predictor._SIM_PACKAGE or {}).get("features"), "mid-term"),
        "registered_versions": {
            "complete_record": len(main_reg.get("versions", [])),
            "mid_term":        len(sim_reg.get("versions", [])),
        },
        "promotion_policy": (
            "Read-only view. Promotion and rollback are CLI-only, behind the "
            "compare_and_promote gate — deliberately not exposed here."
        ),
    }


@app.get("/api/admin/model-health", tags=["Admin"])
async def model_health(
    user: dict         = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """Everything needed to judge whether the deployed models are still healthy.

    Gated with require_head_of_school (Head of Technology OR Head of School),
    matching the other institution-wide admin pages. A Lecturer gets 403.
    """
    from app.ml.check_bias_persistence import collect as collect_bias
    from app.ml.prediction_accuracy_report import summarise as summarise_accuracy
    from app.ml.intervention_outcome_report import collect as collect_interventions

    # Reuse the report's own summarise() on rows from THIS request's session,
    # rather than its collect() (which opens a second engine of its own).
    reconciled = (await db.execute(
        select(Prediction).where(Prediction.actual_pass.is_not(None))
    )).scalars().all()

    return {
        "live_models":      _live_model_summary(),
        "accuracy":         summarise_accuracy(reconciled),
        "fairness":         collect_bias(),
        "interventions":    await collect_interventions(db),
        "generated_at":     datetime.now(timezone.utc).isoformat(),
    }

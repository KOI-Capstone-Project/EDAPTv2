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
import io
import json
import logging
import math
import os
from pathlib import Path
import secrets
import smtplib
import tempfile
import uuid
from typing import Annotated, Optional

import joblib
import pandas as pd
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field, StringConstraints, field_validator
from sqlalchemy import delete, desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import AuditLog, Base, PendingIngest, Prediction, User as UserModel

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SECRET_KEY:           str       = os.getenv("SECRET_KEY", "edapt-dev-secret-key-change-in-production")
if SECRET_KEY == "edapt-dev-secret-key-change-in-production":
    logging.getLogger(__name__).warning(
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
    print(f"[EDAPT] ML model loaded: {_MODEL_NAME} (accuracy {_MODEL_ACCURACY:.4f}, "
          f"{len(_SAFE_SUBJECTS)} safe subjects)")
except Exception as _e:
    print(f"[EDAPT] WARNING: ML model not loaded — {_e}. Run train_model.py first.")

# ── Subject reliability (loaded once at startup) ─────────────────────────────

_RELIABILITY_PATH = Path(__file__).parent.parent.parent / "data" / "subject_reliability.json"
_SUBJECT_RELIABILITY: dict = {"fully_clean": [], "mostly_clean": [], "unreliable": []}

try:
    with open(_RELIABILITY_PATH) as _f:
        _SUBJECT_RELIABILITY = json.load(_f)
except Exception as _e:
    print(f"[EDAPT] WARNING: subject_reliability.json not loaded — {_e}")


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
        print("[EDAPT] Gemini API configured successfully")
    else:
        print("[EDAPT] WARNING: Gemini API key not configured")
except Exception as _e:
    print(f"[EDAPT] WARNING: Gemini API key not configured — {_e}")

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

# Load the bundled development dataset on server start so the demo works without a
# manual upload. The /api/ingest endpoint handles runtime uploads and overwrites _DATA.
_DATA_PATH = Path(__file__).parent.parent.parent / "data" / "Capstone_data_20260729.csv"
try:
    _df = pd.read_csv(_DATA_PATH)
    _df.columns = [c.strip() for c in _df.columns]
    if "MARKPERCENT" in _df.columns:
        _df["MARKPERCENT"] = pd.to_numeric(_df["MARKPERCENT"], errors="coerce")
        _df["PASSED"] = _df["MARKPERCENT"] >= 50
    if "STUDYPERIOD" in _df.columns:
        _df["STUDYPERIOD"] = _df["STUDYPERIOD"].apply(
            lambda x: str(round(float(x), 1)) if pd.notna(x) else ""
        )
    _DATA = _df
    print(f"[EDAPT] Startup data loaded: {len(_DATA):,} rows, {len(_DATA.columns)} columns")
except FileNotFoundError:
    print(f"[EDAPT] ERROR: startup CSV not found at {_DATA_PATH} — upload a dataset via /api/ingest")
except Exception as _e:
    print(f"[EDAPT] ERROR loading startup data: {_e}")

# ── Attendance data store ───────────────────────────────────────────────────
# Wired in as a standard part of startup, same as _DATA above — not a manual
# script someone has to remember to run before attendance endpoints work. One
# row per (STUDENTID_MASKED, SUBJECTCODE, STUDYPERIOD) enrolment, with the
# same real PASS target training uses (via collapse_attempts_to_latest_per_type
# + build_target, not the row-level PASSED column _DATA uses) merged on, so
# an attendance-vs-outcome correlation means the same "pass" everywhere else
# in this project means.
_ATTENDANCE: Optional[pd.DataFrame] = pd.DataFrame()
_ATTENDANCE_PATH = Path(__file__).parent.parent.parent / "data" / "masked_attendance.csv.gz"
try:
    from app.ml.train_model import collapse_attempts_to_latest_per_type, build_target
    from app.ml.build_attendance_features import build_attendance_features

    _att_features = build_attendance_features(
        attendance_path=_ATTENDANCE_PATH, capstone_path=_DATA_PATH
    )
    if not _DATA.empty:
        _collapsed_for_target = collapse_attempts_to_latest_per_type(_DATA.copy())
        _target = build_target(_collapsed_for_target)
        _att_features = _att_features.merge(
            _target, on=["STUDENTID_MASKED", "SUBJECTCODE", "STUDYPERIOD"], how="left"
        )
    _ATTENDANCE = _att_features
    print(f"[EDAPT] Attendance features loaded: {len(_ATTENDANCE):,} enrolments")
except FileNotFoundError:
    print(f"[EDAPT] WARNING: attendance data not found at {_ATTENDANCE_PATH} — attendance endpoints will return empty")
except Exception as _e:
    print(f"[EDAPT] ERROR loading attendance data: {_e}")

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
        print("[EDAPT] Default users seeded")

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
    print("[EDAPT] Database ready")
    if GMAIL_SENDER and GMAIL_APP_PASSWORD:
        print("[EDAPT] Email service configured")
    else:
        print("[EDAPT] WARNING: Email service not configured — forgot password will not work")

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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


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

# ─────────────────────────────────────────────────────────────────────────────
# Auth Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health():
    """Basic liveness probe."""
    return {"status": "ok", "version": "2.0.0"}


@app.get("/api/health", tags=["Health"])
async def api_health():
    """Extended health check that includes row count of the loaded dataset."""
    return {
        "status":  "ok",
        "version": "2.0.0",
        "rows":    len(_DATA) if _DATA is not None else 0,
        "message": "EDAPT API running",
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
    subjects       = db_user.subjects or []
    is_super_admin = bool(db_user.is_super_admin)
    token = _create_token({
        "sub":            db_user.email,
        "role":           db_user.role,
        "name":           db_user.name,
        "subjects":       subjects,
        "is_super_admin": is_super_admin,
    })
    await _append_audit_db(db, user_uid=db_user.email, action_type="Login",
                           status="Success", detail=f"Successful login as {db_user.role}")
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
    except Exception:
        await _append_audit_db(db, user_uid=req.email, action_type="Password Reset Requested",
                               status="Error", detail="Failed to send OTP email")
        raise HTTPException(500, "Failed to send reset email. Please try again later.")

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
            try:
                _INGEST_LOCK_PATH.unlink()
            except FileNotFoundError:
                pass
            continue

        if _time.monotonic() >= deadline:
            raise IngestLockTimeout(
                f"Could not acquire the ingest lock within {_INGEST_LOCK_WAIT_MAX_SECONDS}s — "
                f"another capstone ingest appears to still be in progress."
            )
        _time.sleep(_INGEST_LOCK_POLL_INTERVAL_SECONDS)


def _release_ingest_lock() -> None:
    try:
        _INGEST_LOCK_PATH.unlink()
    except FileNotFoundError:
        pass


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


@app.post("/api/ingest/capstone/analyze", tags=["Ingest"])
async def ingest_capstone_analyze(
    file: UploadFile = File(...),
    user: dict = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """
    Parse + classify a capstone CSV's columns (KEEP/SKIP/NEW) WITHOUT
    committing it to the live dataset. Returns a token; call
    POST /api/ingest/capstone/confirm with it to actually commit.
    """
    from app.ml.column_classification import classify_columns

    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext != "csv":
        raise HTTPException(400, "Unsupported file type. Only .csv files are accepted.")

    content = await file.read()
    err = _reject_upload_common(content, MAX_UPLOAD_BYTES)
    if err:
        await _append_audit_db(db, user_uid=user["sub"], action_type="Data Upload",
                               status="Alert", detail=f"Rejected capstone upload: {err}")
        raise HTTPException(400, err)

    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        await _append_audit_db(db, user_uid=user["sub"], action_type="Data Upload",
                               status="Error", detail=f"Failed to parse capstone CSV: {exc}")
        raise HTTPException(422, "The uploaded file could not be parsed as a valid CSV.")
    df.columns = [c.strip() for c in df.columns]

    from app.ml.column_classification import CAPSTONE_KEEP
    missing_keep = [c for c in CAPSTONE_KEEP if c not in df.columns]
    if missing_keep:
        await _append_audit_db(db, user_uid=user["sub"], action_type="Data Upload",
                               status="Alert",
                               detail=f"Rejected capstone upload: missing required column '{missing_keep[0]}'")
        raise HTTPException(400, f"Missing required column: {missing_keep[0]}")

    classification = classify_columns(df.columns.tolist(), "capstone")

    periods = (
        sorted(df["STUDYPERIOD"].dropna().apply(lambda x: round(float(x), 1)).unique().tolist())
        if "STUDYPERIOD" in df.columns else []
    )
    token = str(uuid.uuid4())
    await _save_pending_ingest(db, "capstone", token, file.filename, content)
    return {
        "token":         token,
        "row_count":     len(df),
        "subjects":      int(df["SUBJECTCODE"].nunique()) if "SUBJECTCODE" in df.columns else 0,
        "periods":       periods,
        "columns":       classification,
        "filename":      file.filename,
    }


@app.post("/api/ingest/capstone/confirm", tags=["Ingest"])
async def ingest_capstone_confirm(
    payload: dict,
    user: dict = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """
    Commit a previously-analyzed capstone upload (by token) to the live
    dataset. Runs the SAME collapse_attempts_to_latest_per_type() logic
    training uses — no attempt-1-only path anywhere in this flow. Writes
    the file to DATA_PATH on disk (required for check_new_period.py /
    train_model.py, both disk-based, to see the new data) and checks
    for a genuinely new study period, registering a retrain candidate
    if so — never auto-promoting.
    """
    global _DATA, _ATTENDANCE

    token = payload.get("token")
    pending_row = await _load_pending_ingest(db, "capstone", token)
    if pending_row is None:
        raise HTTPException(404, "No matching pending capstone upload (or it expired). Analyze the file again.")
    pending_df = pd.read_csv(io.BytesIO(pending_row.csv_bytes))
    pending_filename = pending_row.filename

    df = pending_df.copy()
    if "STUDYPERIOD" in df.columns:
        df["STUDYPERIOD"] = df["STUDYPERIOD"].apply(
            lambda x: str(round(float(x), 1)) if pd.notna(x) else ""
        )
    if "MARKPERCENT" in df.columns:
        df["MARKPERCENT"] = pd.to_numeric(df["MARKPERCENT"], errors="coerce")

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
            if pct == 100.0: return "FULLY_CLEAN"
            if pct >= 90.0:  return "MOSTLY_CLEAN"
            return "UNRELIABLE"
        new_cats = {s: _cat(p) for s, p in stats.items()}
        with open(RELIABILITY_PATH) as f:
            old_rel = json.load(f)
        old_cats = {}
        for s in old_rel.get("fully_clean", []):  old_cats[s] = "FULLY_CLEAN"
        for s in old_rel.get("mostly_clean", []): old_cats[s] = "MOSTLY_CLEAN"
        for s in old_rel.get("unreliable", []):   old_cats[s] = "UNRELIABLE"
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
    # check_new_period.DATA_PATH at it — the same monkey-patch pattern
    # verify_dynamic_period_e2e.py already uses for isolated retrain testing —
    # restoring both afterward regardless of outcome. This is required for
    # check_new_period.py and train_model.py to actually see the newly
    # ingested data (both read DATA_PATH from disk, not from the in-memory
    # _DATA this endpoint also updates).
    import app.ml.train_model as train_model_mod
    train_model_mod.INGESTED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    INGESTED_CAPSTONE_PATH = train_model_mod.INGESTED_DATA_DIR / "ingested_capstone.csv"

    df["PASSED"] = df["MARKPERCENT"] >= 50

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
        pending_df.to_csv(INGESTED_CAPSTONE_PATH, index=False)
        _DATA = df
        _ATTENDANCE = new_attendance

        original_paths = {
            "train_model": train_model_mod.DATA_PATH,
            "check_new_period": check_new_period_mod.DATA_PATH,
        }
        retrain_info = {"triggered": False, "reason": None, "candidate_version": None}
        try:
            train_model_mod.DATA_PATH = INGESTED_CAPSTONE_PATH
            check_new_period_mod.DATA_PATH = INGESTED_CAPSTONE_PATH

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
    finally:
        _release_ingest_lock()

    await _delete_pending_ingest(db, "capstone")

    await _append_audit_db(
        db, user_uid=user["sub"], action_type="Data Upload", status="Success",
        detail=f"{len(df):,} rows ingested from {pending_filename} "
               f"(subjects reclassified: {subjects_reclassified}, retrain triggered: {retrain_info['triggered']})",
    )
    return {
        "row_count":              len(df),
        "columns":                list(df.columns),
        "subjects_reclassified":  subjects_reclassified,
        "retrain":                retrain_info,
        "promotion_note":         "Model promotion stays manual",
        "message":                f"{len(df):,} rows successfully loaded",
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


@app.post("/api/ingest/attendance/analyze", tags=["Ingest"])
async def ingest_attendance_analyze(
    file: UploadFile = File(...),
    user: dict = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """
    Parse + classify an attendance CSV's columns (KEEP/SKIP/NEW) WITHOUT
    committing it. A separate, clearly distinct slot from the capstone
    analyze endpoint — the two file types are never accepted through the
    same endpoint, so they can't be cross-uploaded into the wrong slot.
    Returns a token; call POST /api/ingest/attendance/confirm with it to
    actually commit.
    """
    from app.ml.column_classification import classify_columns

    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext != "csv":
        raise HTTPException(400, "Unsupported file type. Only .csv files are accepted.")

    content = await file.read()
    err = _reject_upload_common(content, MAX_ATTENDANCE_UPLOAD_BYTES)
    if err:
        await _append_audit_db(db, user_uid=user["sub"], action_type="Data Upload",
                               status="Alert", detail=f"Rejected attendance upload: {err}")
        raise HTTPException(400, err)

    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        await _append_audit_db(db, user_uid=user["sub"], action_type="Data Upload",
                               status="Error", detail=f"Failed to parse attendance CSV: {exc}")
        raise HTTPException(422, "The uploaded file could not be parsed as a valid CSV.")
    df.columns = [c.strip() for c in df.columns]

    # Required for aggregation specifically (a functional subset of
    # ATTENDANCE_KEEP — cls_session_no is in the locked KEEP schema but
    # not needed for the student-subject-period aggregation this pipeline
    # actually does).
    required = ["STUDENTID_MASKED", "course", "study_period_code", "year", "attendance_code"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        await _append_audit_db(db, user_uid=user["sub"], action_type="Data Upload",
                               status="Alert",
                               detail=f"Rejected attendance upload: missing required column '{missing[0]}'")
        raise HTTPException(400, f"Missing required column: {missing[0]}")

    classification = classify_columns(df.columns.tolist(), "attendance")

    token = str(uuid.uuid4())
    await _save_pending_ingest(db, "attendance", token, file.filename, content)
    return {
        "token":     token,
        "row_count": len(df),
        "columns":   classification,
        "filename":  file.filename,
    }


@app.post("/api/ingest/attendance/confirm", tags=["Ingest"])
async def ingest_attendance_confirm(
    payload: dict,
    user: dict = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    """Commit a previously-analyzed attendance upload (by token) to the live _ATTENDANCE table."""
    global _ATTENDANCE

    token = payload.get("token")
    pending_row = await _load_pending_ingest(db, "attendance", token)
    if pending_row is None:
        raise HTTPException(404, "No matching pending attendance upload (or it expired). Analyze the file again.")

    from app.ml.train_model import collapse_attempts_to_latest_per_type, build_target
    from app.ml.build_attendance_features import build_attendance_features

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=True) as tmp:
        tmp.write(pending_row.csv_bytes)
        tmp.flush()
        att_features = build_attendance_features(
            attendance_path=Path(tmp.name), capstone_path=_DATA_PATH,
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
    await _delete_pending_ingest(db, "attendance")

    await _append_audit_db(
        db, user_uid=user["sub"], action_type="Data Upload", status="Success",
        detail=f"{len(att_features):,} attendance enrolments ingested from {pending_row.filename} "
               f"(match rate vs current capstone data: {match_rate}%)",
    )
    return {
        "row_count":  len(att_features),
        "columns":    list(att_features.columns),
        "match_rate": match_rate,
        "message":    f"{len(att_features):,} attendance enrolments loaded, {match_rate}% match rate against current capstone data",
    }


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
POPULATION_ALL_TRACKED  = "all attendance-tracked enrolments (course+period+year filtered) — includes students with no matching capstone assessment record for that subject+period"
POPULATION_WITH_OUTCOME = "enrolments with BOTH attendance data AND a matching capstone assessment record (a real PASS/FAIL target)"


@app.get("/api/dashboard/attendance-distribution", tags=["Dashboard"])
async def attendance_distribution(
    subject:   Optional[str] = Query(None),
    trimester: Optional[str] = Query(None),
    year:      Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """Return count of enrolments in each attendance-rate band. Population: ALL attendance-tracked enrolments, not restricted to those with a matching assessment record — see POPULATION_ALL_TRACKED."""
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
    """Return attendance-rate vs pass/fail outcome correlation for the current scope. Population: only enrolments with a matching assessment record — see POPULATION_WITH_OUTCOME."""
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
    """Return average attendance rate per subject, sorted ascending. Admin sees all subjects; Lecturer sees only their assigned subjects (via _role_filter). Population: ALL attendance-tracked enrolments — see POPULATION_ALL_TRACKED."""
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

    # attendance_rate: if the caller (What-If simulator, or an older client)
    # didn't supply one, default to this subject's real average
    # ATTENDANCE_RATE rather than silently using 0 or requiring every
    # hypothetical scenario to specify it. attendance_rate_is_default in the
    # response lets the frontend show this was a default, not user input.
    attendance_rate_is_default = req.attendance_rate is None
    attendance_rate = req.attendance_rate
    if attendance_rate_is_default:
        attendance_rate = _subject_average_attendance_rate(req.subject)

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
        raise HTTPException(503, "ML model not loaded. Run train_model.py first.")

    result["attendance_rate_is_default"] = attendance_rate_is_default and result.get("attendance_rate_used") is not None

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

    period_total_weight = (
        df_period.drop_duplicates(subset=["ASSESSMENTTYPECODE"])["WEIGHTING"].sum()
    )
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

            # This student's real, full attendance rate — safe for a
            # complete record (same closed-snapshot premise
            # build_early_features() relies on). Falls back to the subject
            # average only if this enrolment has no attendance row.
            attendance_rate = None
            if _ATTENDANCE is not None and not _ATTENDANCE.empty and "ATTENDANCE_RATE" in _ATTENDANCE.columns:
                match = _ATTENDANCE[
                    (_ATTENDANCE["STUDENTID_MASKED"] == student_id)
                    & (_ATTENDANCE["SUBJECTCODE"] == subject)
                    & (_ATTENDANCE["STUDYPERIOD"] == study_period)
                ]
                if not match.empty:
                    attendance_rate = float(match["ATTENDANCE_RATE"].iloc[0])
            if attendance_rate is None:
                attendance_rate = _subject_average_attendance_rate(subject)

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
            attendance_rate = _truncated_attendance_rate(
                str(student_id), subject, study_period, coverage_fraction
            )
            if attendance_rate is None:
                attendance_rate = _subject_average_attendance_rate(subject)

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
    if action_type:   query = query.where(AuditLog.action_type == action_type)
    if status_filter: query = query.where(AuditLog.status == status_filter)
    result = await db.execute(query)
    logs   = result.scalars().all()

    # Resolve each user_uid to its current role in one batch query so the
    # frontend never has to infer role from UID patterns (which fails for
    # real email addresses like principal@koi.edu.au).
    uids = {log.user_uid for log in logs}
    role_rows = await db.execute(
        select(UserModel.email, UserModel.role).where(UserModel.email.in_(uids))
    )
    role_map: dict[str, str] = {email: role for email, role in role_rows.all()}

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

"""
EDAPT v2 — FastAPI Backend (self-contained)

Auth: PostgreSQL User table + bcrypt + JWT.
Data: CSV loaded into _DATA (pandas DataFrame) via POST /api/ingest.
Dashboard: 8 endpoints that slice _DATA by role + query filters.
"""

import asyncio
import io
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import AuditLog, Base, User as UserModel

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

SECRET_KEY           = os.getenv("SECRET_KEY", "edapt-dev-secret-key-change-in-production")
if SECRET_KEY == "edapt-dev-secret-key-change-in-production":
    logging.getLogger(__name__).warning(
        "SECRET_KEY is set to the insecure default dev value — set a strong SECRET_KEY env var before deploying"
    )
ALGORITHM            = "HS256"
TOKEN_EXPIRE_MINUTES = 480
CORS_ORIGINS         = ["http://localhost:3000", "http://localhost:5173", "http://localhost:80", "http://127.0.0.1:3000", "http://127.0.0.1:5173"]

# ── ML model (loaded once at startup) ────────────────────────────────────────

_ML_DIR  = Path(__file__).parent / "ml"
_MODEL   = None
_SUBJ_DIFFICULTY: dict = {}
_MODEL_NAME     = "Random Forest"
_MODEL_ACCURACY = 0.0
_MEDIAN_ASSESS2 = 60.0

try:
    _MODEL            = joblib.load(_ML_DIR / "best_model.pkl")
    _SUBJ_DIFFICULTY  = joblib.load(_ML_DIR / "subject_difficulty.pkl")
    _meta             = joblib.load(_ML_DIR / "model_meta.pkl")
    _MODEL_NAME       = _meta.get("name", "Random Forest")
    _MODEL_ACCURACY   = _meta.get("accuracy", 0.0)
    _MEDIAN_ASSESS2   = _meta.get("median_assess2", 60.0)
except Exception:
    pass  # model not yet trained — /api/predict returns 503

# ── Gemini ────────────────────────────────────────────────────────────────────

_flash_model = None
_pro_model   = None
_GEMINI_TOKEN_LOG: list[dict] = []

try:
    import google.generativeai as _genai
    _gemini_key = os.getenv("GEMINI_API_KEY", "")
    if _gemini_key and "your-gemini" not in _gemini_key:
        _genai.configure(api_key=_gemini_key)
        _flash_model = _genai.GenerativeModel("gemini-1.5-flash")
        _pro_model   = _genai.GenerativeModel("gemini-1.5-pro")
except Exception:
    pass  # Gemini unavailable — endpoints return fallback text

# ── Auth ──────────────────────────────────────────────────────────────────────

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _validate_password(password: str) -> None:
    if len(password) < 10:
        raise HTTPException(400, "Password must be at least 10 characters.")
    if not any(c.isupper() for c in password):
        raise HTTPException(400, "Password must contain at least one uppercase letter.")
    if not any(c.islower() for c in password):
        raise HTTPException(400, "Password must contain at least one lowercase letter.")
    if not any(c.isdigit() for c in password):
        raise HTTPException(400, "Password must contain at least one number.")


_REVOKED_TOKENS: set[str] = set()

_FAILED_LOGINS: dict[str, list] = {}
_MAX_ATTEMPTS    = 5
_LOCKOUT_MINUTES = 15


def _check_lockout(email: str) -> None:
    cutoff  = datetime.now(timezone.utc) - timedelta(minutes=_LOCKOUT_MINUTES)
    recent  = [t for t in _FAILED_LOGINS.get(email, []) if t > cutoff]
    _FAILED_LOGINS[email] = recent
    if len(recent) >= _MAX_ATTEMPTS:
        wait = _LOCKOUT_MINUTES - int((datetime.now(timezone.utc) - min(recent)).total_seconds() / 60)
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {max(1, wait)} minute(s).",
        )


def _record_failed_attempt(email: str) -> None:
    _FAILED_LOGINS.setdefault(email, []).append(datetime.now(timezone.utc))


# ── In-memory data store ──────────────────────────────────────────────────────

# Global shared state — all roles read from this single DataFrame. Role filtering is applied
# per request in _role_filter. Head of Technology and Head of School see all rows.
# Lecturers see only rows matching their assigned subjects.
_DATA: Optional[pd.DataFrame] = pd.DataFrame()

# ── Startup data load ─────────────────────────────────────────────────────────
# This loads the bundled development dataset automatically on server start so the
# demo works without a manual upload. The /api/ingest endpoint handles runtime
# uploads and overwrites _DATA; both paths intentionally coexist.

_DATA_PATH = Path(__file__).parent.parent.parent / "data" / "Capstone_data_20260324.csv"
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
    print(f"[EDAPT] No startup CSV found at {_DATA_PATH} — upload via /api/ingest")
except Exception as _e:
    print(f"[EDAPT] ERROR loading startup data: {_e}")

# ── Database setup ────────────────────────────────────────────────────────────

_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://sangamgurung@localhost:5432/edapt",
)
_engine = create_async_engine(_DB_URL, echo=False, pool_pre_ping=True)
_AsyncSession = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
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
    db.add(AuditLog(user_uid=user_uid, action_type=action_type, status=status, detail=detail))
    await db.commit()


async def _seed_default_users() -> None:
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
                subjects=[],
            ),
            UserModel(
                email="user",
                name="Demo Lecturer",
                hashed_password=_pwd.hash("Lect@2025!"),
                role="Lecturer",
                is_active=True,
                subjects=["ICT104", "ICT201", "ICT301"],
            ),
            UserModel(
                email="hos",
                name="Demo Head of School",
                hashed_password=_pwd.hash("HoS@2025!"),
                role="Head of School",
                is_active=True,
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
    subject: Optional[str] = None,
    trimester: Optional[str] = None,
    year: Optional[str] = None,
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

# ── Pydantic models ───────────────────────────────────────────────────────────

# Strict email pattern: localpart@domain.extension (extension ≥ 2 chars)
_EMAIL_REGEX = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z0-9]{2,}$'

# OTP email verification to be implemented in production with SMTP integration.
class LoginRequest(BaseModel):
    # Accepts both email addresses and plain staff IDs (e.g. "admin").
    # Pattern blocks unsafe characters without requiring full email format.
    email:    str = Field(..., max_length=254, pattern=r'^[a-zA-Z0-9._%+@\-]+$')
    password: str = Field(..., max_length=128)

# OTP email verification to be implemented in production with SMTP integration.
class CreateUserRequest(BaseModel):
    email:    str = Field(..., max_length=254, pattern=_EMAIL_REGEX)
    password: str
    name:     Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    role:     str = "Lecturer"
    subjects: list[str] = []

    @field_validator('email', mode='before')
    @classmethod
    def normalise_email(cls, v):
        if isinstance(v, str):
            return v.lower().strip()
        return v

class PredictRequest(BaseModel):
    subject:      str
    assess1_mark: float = Field(..., ge=0.0, le=100.0)
    assess2_mark: Optional[float] = Field(None, ge=0.0, le=100.0)

class GeminiAlertRequest(BaseModel):
    subject:   Optional[str] = Field(None, max_length=20)
    trimester: Optional[str] = Field(None, max_length=10)

class GeminiAnalyseRequest(BaseModel):
    subject:   str = Field(..., max_length=20)
    trimester: Optional[str] = Field(None, max_length=10)

class GeminiAskRequest(BaseModel):
    question:  str = Field(..., max_length=500)
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

# ── JWT helpers ───────────────────────────────────────────────────────────────

def _create_token(payload: dict) -> str:
    data = payload.copy()
    data["exp"] = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def _decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="EDAPT v2 API", version="2.0.0")


@app.on_event("startup")
async def _startup():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _seed_default_users()
    print("[EDAPT] Database ready")


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# ── Auth dependencies ─────────────────────────────────────────────────────────

async def get_current_user(token: str = Depends(_oauth2)) -> dict:
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
    if user.get("role") != "Head of Technology":
        raise HTTPException(status_code=403, detail="Only Head of Technology can access this feature.")
    return user


async def require_head_of_school(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in {"Head of Technology", "Head of School"}:
        raise HTTPException(status_code=403, detail="Only Head of Technology or Head of School can access this feature.")
    return user


async def require_super_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("is_super_admin") is not True:
        raise HTTPException(status_code=403, detail="Only the system administrator can access this feature.")
    return user

# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/api/health", tags=["Health"])
async def api_health():
    return {
        "status": "ok",
        "version": "2.0.0",
        "rows": len(_DATA) if _DATA is not None else 0,
        "message": "EDAPT API running",
    }


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.post("/api/auth/login", tags=["Auth"])
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    _check_lockout(req.email)
    result = await db.execute(select(UserModel).where(UserModel.email == req.email))
    db_user = result.scalar_one_or_none()

    if not db_user or not _pwd.verify(req.password, db_user.hashed_password):
        _record_failed_attempt(req.email)
        await _append_audit_db(db, user_uid=req.email, action_type="Login Failed",
                               status="Alert", detail="Invalid credentials")
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not db_user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated. Contact your administrator.")

    _FAILED_LOGINS.pop(req.email, None)
    subjects       = db_user.subjects or []
    is_super_admin = db_user.email == "admin"
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


# ── Generic data ──────────────────────────────────────────────────────────────

@app.get("/api/data", tags=["Data"])
async def get_data(user: dict = Depends(get_current_user)):
    if _DATA is None or _DATA.empty:
        return {"columns": [], "rows": [], "total": 0, "filtered": 0}
    df = _role_filter(_DATA.copy(), user)
    return {"columns": list(df.columns), "rows": df.head(1000).fillna("").to_dict("records"), "total": len(df), "filtered": min(len(df), 1000)}


@app.get("/api/summary", tags=["Data"])
async def get_summary(user: dict = Depends(get_current_user)):
    if _DATA is None or _DATA.empty:
        return {"data": []}
    df = _role_filter(_DATA.copy(), user)
    if "SUBJECTCODE" not in df.columns:
        return {"data": []}
    mark_col = next((c for c in df.columns if "PCT" in c.upper() or "PERCENT" in c.upper() or "MARKPERCENT" in c.upper()), None)
    grouped = df.groupby("SUBJECTCODE")
    result = []
    for code, grp in grouped:
        entry: dict = {"subject_code": code, "row_count": len(grp)}
        if mark_col:
            entry["avg_mark"] = round(grp[mark_col].mean(), 1)
        result.append(entry)
    result.sort(key=lambda x: x["subject_code"])
    return {"data": result}


@app.get("/api/filters", tags=["Data"])
async def get_filters(user: dict = Depends(get_current_user)):
    if user.get("role") == "Lecturer":
        return {"subjects": user.get("subjects", [])}
    if _DATA is not None and "SUBJECTCODE" in _DATA.columns:
        return {"subjects": sorted(_DATA["SUBJECTCODE"].dropna().unique().tolist())}
    return {"subjects": []}


# ── Ingest (admin only) ───────────────────────────────────────────────────────

@app.post("/api/ingest", tags=["Ingest"])
async def ingest_dataset(
    file: UploadFile = File(...),
    user: dict = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    global _DATA
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext != "csv":
        await _append_audit_db(db, user_uid=user["sub"], action_type="Data Upload",
                               status="Alert", detail=f"Rejected upload: unsupported file type '.{ext}'")
        raise HTTPException(400, "Unsupported file type. Only .csv files are accepted.")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        await _append_audit_db(db, user_uid=user["sub"], action_type="Data Upload",
                               status="Alert", detail="Rejected upload: file exceeds 50 MB limit")
        raise HTTPException(400, "File exceeds the 50 MB limit.")

    if len(content) == 0:
        await _append_audit_db(db, user_uid=user["sub"], action_type="Data Upload",
                               status="Alert", detail="Rejected upload: file is empty")
        raise HTTPException(400, "Uploaded file is empty.")

    head = content[:2000]
    _BINARY_SIGS = (b"PK", b"%PDF", b"\x89PNG", b"\xff\xd8", b"\x42\x4d")
    if any(head.startswith(sig) for sig in _BINARY_SIGS) or b"," not in head:
        await _append_audit_db(db, user_uid=user["sub"], action_type="Data Upload",
                               status="Alert", detail="Rejected upload: file does not appear to be a valid CSV")
        raise HTTPException(400, "File does not appear to be a valid CSV.")

    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as exc:
        await _append_audit_db(db, user_uid=user["sub"], action_type="Data Upload",
                               status="Error", detail=f"Failed to parse CSV: {exc}")
        raise HTTPException(422, "The uploaded file could not be parsed as a valid CSV.")

    df.columns = [c.strip() for c in df.columns]

    REQUIRED_COLS = [
        "STUDYPACKAGEASSESSMENTID", "ASSESSMENTTYPECODE", "ATTEMPTNUMBER",
        "ASSESSMENTMARK", "MAXMARK", "WEIGHTING", "GENDERCODE", "AGEGROUP",
        "STUDYPERIOD", "SUBJECTCODE", "CLASSGROUP", "MARKPERCENT",
        "STUDENTID_MASKED", "COUNTRY_MASKED",
    ]
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        await _append_audit_db(db, user_uid=user["sub"], action_type="Data Upload",
                               status="Alert", detail=f"Rejected upload: missing column '{missing[0]}'")
        raise HTTPException(400, f"Missing required column: {missing[0]}")

    if "STUDYPERIOD" in df.columns:
        df["STUDYPERIOD"] = df["STUDYPERIOD"].apply(
            lambda x: str(round(float(x), 1)) if pd.notna(x) else ""
        )
    if "MARKPERCENT" in df.columns:
        df["MARKPERCENT"] = pd.to_numeric(df["MARKPERCENT"], errors="coerce")

    df["PASSED"] = df["MARKPERCENT"] >= 50
    _DATA = df

    await _append_audit_db(db, user_uid=user["sub"], action_type="Data Upload",
                           status="Success", detail=f"{len(df):,} rows ingested from {file.filename}")
    return {
        "row_count": len(df),
        "columns":   list(df.columns),
        "message":   f"{len(df):,} rows successfully loaded",
    }


@app.get("/api/ingest/preview", tags=["Ingest"])
async def ingest_preview(
    page:      int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    user: dict = Depends(require_head_of_school),
):
    global _DATA
    if _DATA is None or _DATA.empty:
        return {"total": 0, "page": page, "page_size": page_size, "total_pages": 0, "columns": [], "data": []}
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


# ── Audit log (admin only) ────────────────────────────────────────────────────

@app.get("/api/audit-logs", tags=["Audit"])
async def get_audit_logs(
    action_type:   Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None),
    user: dict = Depends(require_admin),
    db:   AsyncSession = Depends(get_db),
):
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


# ── User management (admin only) ──────────────────────────────────────────────

@app.get("/api/users", tags=["Admin"])
async def list_users(
    user: dict = Depends(require_super_admin),
    db:   AsyncSession = Depends(get_db),
):
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

    detail = (f"{payload.role} account created: {payload.email}"
              + (f" assigned to {', '.join(subjects)}" if subjects else ""))
    await _append_audit_db(db, user_uid=user["sub"], action_type="User Created",
                           status="Success", detail=detail)
    return {
        "message": f"{payload.role} account created",
        "user":    {"email": payload.email, "name": payload.name, "role": payload.role, "subjects": subjects},
    }


@app.put("/api/users/{email}", tags=["Admin"])
async def update_user(
    email:   str,
    payload: UpdateUserRequest,
    user: dict = Depends(require_super_admin),
    db:   AsyncSession = Depends(get_db),
):
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


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/dashboard/summary", tags=["Dashboard"])
async def dashboard_summary(
    subject:   Optional[str] = Query(None),
    trimester: Optional[str] = Query(None),
    year:      Optional[str] = Query(None),
    classgroup: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    empty = {"total_students": 0, "total_subjects": 0, "avg_mark": 0.0,
             "avg_mark_prev": None, "pass_rate": 0.0, "pass_rate_prev": None,
             "at_risk_count": 0, "countries_count": 0}
    if _DATA is None or _DATA.empty:
        return empty

    df = _query_filter(_role_filter(_DATA.copy(), user), subject, trimester, year, classgroup)
    df = df.dropna(subset=["MARKPERCENT"])
    if df.empty:
        return empty

    avg_mark  = _safe(df["MARKPERCENT"].mean())
    pass_rate = _safe((df["MARKPERCENT"] >= 50).mean() * 100)
    countries = int(df["COUNTRY_MASKED"].nunique()) if user.get("role") in {"Head of Technology", "Head of School"} and "COUNTRY_MASKED" in df.columns else 0

    # Previous trimester change (only meaningful when a specific trimester is selected)
    avg_mark_prev = pass_rate_prev = None
    if trimester:
        prev = _prev_period(trimester)
        if prev:
            df_p = _query_filter(_role_filter(_DATA.copy(), user), subject, prev, None, classgroup)
            df_p = df_p.dropna(subset=["MARKPERCENT"])
            if not df_p.empty:
                avg_mark_prev = _safe(df_p["MARKPERCENT"].mean())
                pass_rate_prev = _safe((df_p["MARKPERCENT"] >= 50).mean() * 100)

    return {
        "total_students":  int(df["STUDENTID_MASKED"].nunique()) if "STUDENTID_MASKED" in df.columns else 0,
        "total_subjects":  int(df["SUBJECTCODE"].nunique()) if "SUBJECTCODE" in df.columns else 0,
        "avg_mark":        round(avg_mark, 1)  if avg_mark  is not None else 0.0,
        "avg_mark_prev":   round(avg_mark_prev, 1) if avg_mark_prev is not None else None,
        "pass_rate":       round(pass_rate, 1) if pass_rate is not None else 0.0,
        "pass_rate_prev":  round(pass_rate_prev, 1) if pass_rate_prev is not None else None,
        "at_risk_count":   int((df["MARKPERCENT"] < 50).sum()),
        "countries_count": countries,
    }


@app.get("/api/dashboard/grade-distribution", tags=["Dashboard"])
async def grade_distribution(
    subject:   Optional[str] = Query(None),
    trimester: Optional[str] = Query(None),
    year:      Optional[str] = Query(None),
    classgroup: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
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
    if _DATA is None or _DATA.empty:
        return {"data": [{"period": p, "institution_avg": None, "subject_avg": None} for p in PERIODS_ORDER]}

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
            "period": period,
            "institution_avg": round(inst, 1) if inst is not None else None,
            "subject_avg":     round(subj, 1) if subj is not None else None,
        })
    return {"data": result}


@app.get("/api/dashboard/assessment-comparison", tags=["Dashboard"])
async def assessment_comparison(
    subject:   Optional[str] = Query(None),
    trimester: Optional[str] = Query(None),
    year:      Optional[str] = Query(None),
    classgroup: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    if _DATA is None or "ASSESSMENTTYPECODE" not in _DATA.columns:
        return {"data": []}

    df = _query_filter(_role_filter(_DATA.copy(), user), subject, trimester, year, classgroup)
    df = df.dropna(subset=["MARKPERCENT", "ASSESSMENTTYPECODE"])

    grp   = df.groupby("ASSESSMENTTYPECODE")["MARKPERCENT"]
    avg_s = grp.mean().round(1)
    pr_s  = grp.apply(lambda x: round((x >= 50).mean() * 100, 1))
    items = [{"type": t, "avg_mark": float(avg_s[t]), "pass_rate": float(pr_s[t])} for t in avg_s.index]
    return {"data": items, "items": items}


@app.get("/api/dashboard/pass-fail", tags=["Dashboard"])
async def pass_fail(
    subject:   Optional[str] = Query(None),
    trimester: Optional[str] = Query(None),
    year:      Optional[str] = Query(None),
    classgroup: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    if _DATA is None or _DATA.empty:
        return {"pass_count": 0, "fail_count": 0, "pass_rate": 0.0}

    df = _query_filter(_role_filter(_DATA.copy(), user), subject, trimester, year, classgroup)
    df = df.dropna(subset=["MARKPERCENT"])

    pass_count = int((df["MARKPERCENT"] >= 50).sum())
    fail_count = int((df["MARKPERCENT"] <  50).sum())
    total = pass_count + fail_count
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
    if _DATA is None or "SUBJECTCODE" not in _DATA.columns:
        return {"data": []}

    df = _DATA.dropna(subset=["MARKPERCENT"])
    df = df.copy()
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
    if _DATA is None or "CLASSGROUP" not in _DATA.columns:
        return {"classgroups": []}
    df = _DATA.copy()
    if subject and "SUBJECTCODE" in df.columns:
        df = df[df["SUBJECTCODE"] == subject]
    return {"classgroups": sorted(df["CLASSGROUP"].dropna().unique().tolist())}


# ─────────────────────────────────────────────────────────────────────────────
# EXPLORER ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

def _str_val(val) -> str:
    """Convert a pandas cell value to str, coercing NaN → empty string."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return ""
    return str(val)


def _explorer_filter(
    df: pd.DataFrame,
    subject:         Optional[str] = None,
    assessment_type: Optional[str] = None,
    passed:          Optional[str] = None,
    trimester:       Optional[str] = None,
    search:          Optional[str] = None,
    country:         Optional[str] = None,
    gender:          Optional[str] = None,
    age_group:       Optional[str] = None,
    is_admin:        bool = False,
) -> pd.DataFrame:
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
    if is_admin:
        if country and "COUNTRY_MASKED" in df.columns:
            df = df[df["COUNTRY_MASKED"] == country]
        if gender and "GENDERCODE" in df.columns:
            df = df[df["GENDERCODE"] == gender]
        if age_group and "AGEGROUP" in df.columns:
            df = df[df["AGEGROUP"] == age_group]
    return df


def _row_to_record(row: dict, is_admin: bool) -> dict:
    mp = row.get("MARKPERCENT")
    try:
        passed = bool(float(mp) >= 50) if mp is not None else False
    except (TypeError, ValueError):
        passed = False
    record: dict = {
        "student_id":      _str_val(row.get("STUDENTID_MASKED")),
        "subject":         _str_val(row.get("SUBJECTCODE")),
        "assessment_type": _str_val(row.get("ASSESSMENTTYPECODE")),
        "study_period":    _str_val(row.get("STUDYPERIOD")),
        "mark_percent":    _safe(mp),
        "assessment_mark": _safe(row.get("ASSESSMENTMARK")),
        "max_mark":        _safe(row.get("MAXMARK")),
        "passed":          passed,
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
    user: dict = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    if _DATA is None or _DATA.empty:
        return {"total": 0, "page": page, "page_size": page_size, "total_pages": 0, "data": []}

    is_admin = user.get("role") in {"Head of Technology", "Head of School"}
    df = _role_filter(_DATA.copy(), user)
    df = _explorer_filter(df, subject, assessment_type, passed, trimester,
                          search, country, gender, age_group, is_admin)

    total       = len(df)
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    start       = (page - 1) * page_size
    page_df     = df.iloc[start : start + page_size]

    if any([subject, assessment_type, passed, trimester, search, country, gender, age_group]):
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
    is_admin = user.get("role") in {"Head of Technology", "Head of School"}

    if _DATA is None or _DATA.empty:
        return {
            "subjects": user.get("subjects", []) if not is_admin else [],
            "assessment_types": [], "trimesters": [],
            "countries": [], "genders": [], "age_groups": [],
        }

    df_role = _role_filter(_DATA.copy(), user)

    subjects = sorted(df_role["SUBJECTCODE"].dropna().unique().tolist()) \
        if "SUBJECTCODE" in df_role.columns else []
    assessment_types = sorted(df_role["ASSESSMENTTYPECODE"].dropna().unique().tolist()) \
        if "ASSESSMENTTYPECODE" in df_role.columns else []
    trimesters = [p for p in PERIODS_ORDER
                  if "STUDYPERIOD" in df_role.columns and p in df_role["STUDYPERIOD"].values]

    countries  = sorted(_DATA["COUNTRY_MASKED"].dropna().unique().tolist()) \
        if is_admin and "COUNTRY_MASKED" in _DATA.columns else []
    genders    = sorted(_DATA["GENDERCODE"].dropna().unique().tolist()) \
        if is_admin and "GENDERCODE" in _DATA.columns else []
    age_groups = sorted(_DATA["AGEGROUP"].dropna().unique().tolist()) \
        if is_admin and "AGEGROUP" in _DATA.columns else []

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
    student_id: str,
    subject:    Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    if _DATA is None or "STUDENTID_MASKED" not in _DATA.columns:
        raise HTTPException(404, "Student not found")

    is_admin = user.get("role") in {"Head of Technology", "Head of School"}
    df = _role_filter(_DATA.copy(), user)
    df = df[df["STUDENTID_MASKED"].astype(str) == str(student_id)]
    if subject and "SUBJECTCODE" in df.columns:
        df = df[df["SUBJECTCODE"] == subject]
    df = df.dropna(subset=["MARKPERCENT"])

    if df.empty:
        raise HTTPException(404, "Student not found or not in your scope")

    avg_mark      = _safe(df["MARKPERCENT"].mean())
    overall_passed = bool(float(avg_mark) >= 50) if avg_mark is not None else False
    records        = [_row_to_record(r, is_admin) for r in df.to_dict("records")]

    # Per-period trend
    trend_grp = df.groupby("STUDYPERIOD")["MARKPERCENT"].mean().round(1)
    trend = [
        {"period": p, "mark": _safe(trend_grp.get(p))}
        for p in PERIODS_ORDER if p in trend_grp.index
    ]

    # Peer comparison
    subject_codes = df["SUBJECTCODE"].dropna().unique().tolist() if "SUBJECTCODE" in df.columns else []
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
    user: dict = Depends(require_head_of_school),
    db:   AsyncSession = Depends(get_db),
):
    if _DATA is None or _DATA.empty:
        raise HTTPException(404, "No data loaded")

    df = _explorer_filter(
        _DATA.copy(), subject, assessment_type, passed, trimester,
        search, country, gender, age_group, is_admin=True,
    )

    filters_used = [f"{k}={v}" for k, v in [
        ("subject", subject), ("assessment_type", assessment_type),
        ("passed", passed),   ("trimester", trimester),
        ("country", country), ("gender", gender), ("age_group", age_group),
    ] if v]
    filter_str = ", ".join(filters_used) or "none"

    await _append_audit_db(
        db, user_uid=user["sub"], action_type="Export", status="Success",
        detail=f"Exported {len(df):,} records with filters: {filter_str}",
    )

    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    fname = f"edapt_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# GEMINI HELPER
# ─────────────────────────────────────────────────────────────────────────────

async def _gemini_call(model, prompt: str) -> tuple[str, int]:
    """Run a synchronous Gemini SDK call in a thread pool. Returns (text, tokens)."""
    if model is None:
        return "AI insight unavailable.", 0
    try:
        response = await asyncio.to_thread(model.generate_content, prompt)
        text   = response.text.strip()
        tokens = getattr(getattr(response, "usage_metadata", None), "total_token_count", 0)
        _GEMINI_TOKEN_LOG.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tokens": int(tokens),
            "model": getattr(model, "model_name", "unknown"),
        })
        return text, int(tokens)
    except Exception:
        return "AI insight unavailable.", 0


# ─────────────────────────────────────────────────────────────────────────────
# PREDICTOR ENDPOINT
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/predict", tags=["ML"])
async def predict_outcome(req: PredictRequest, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if _MODEL is None:
        raise HTTPException(503, "ML model not loaded. Run backend/app/ml/train_model.py first.")

    is_admin  = user.get("role") in {"Head of Technology", "Head of School"}
    subj_list = user.get("subjects", [])

    # Lecturer must own the subject
    if not is_admin and req.subject not in subj_list:
        raise HTTPException(403, "You are not assigned to that subject.")

    assess2 = req.assess2_mark if req.assess2_mark is not None else _MEDIAN_ASSESS2
    subj_diff   = _SUBJ_DIFFICULTY.get(req.subject, 0.3)
    trim_num    = 9  # current period = 25.3

    features = [[req.assess1_mark, assess2, subj_diff, trim_num]]
    proba    = float(_MODEL.predict_proba(features)[0][1])
    pct      = round(proba * 100, 1)

    if proba >= 0.65:
        risk_level, risk_colour, prediction = "Safe",      "green", "Likely to Pass"
    elif proba >= 0.40:
        risk_level, risk_colour, prediction = "At Risk",   "amber", "Borderline"
    else:
        risk_level, risk_colour, prediction = "High Risk", "red",   "High Risk of Failing"

    # Confidence: count training-like records within ±10% of assess1
    conf_count = 0
    if _DATA is not None and "MARKPERCENT" in _DATA.columns:
        lo, hi = req.assess1_mark - 10, req.assess1_mark + 10
        df_subj = _DATA[_DATA["SUBJECTCODE"] == req.subject] if "SUBJECTCODE" in _DATA.columns else _DATA
        conf_count = int(((df_subj["MARKPERCENT"] >= lo) & (df_subj["MARKPERCENT"] <= hi)).sum())

    # Subject pass rate for the Gemini prompt
    pass_rate_pct = round((1 - subj_diff) * 100, 1)

    # Gemini one-sentence advice
    advice_prompt = (
        f"Student in {req.subject} scored {req.assess1_mark:.1f}% in Assessment 1. "
        f"Pass probability: {pct}%. Subject average pass rate: {pass_rate_pct}%. "
        "Write ONE sentence of advice for the lecturer. Be specific and actionable."
    )
    gemini_advice, _ = await _gemini_call(_flash_model, advice_prompt)

    result: dict = {
        "pass_probability":   pct,
        "prediction":         prediction,
        "risk_level":         risk_level,
        "risk_colour":        risk_colour,
        "confidence_records": conf_count,
        "gemini_advice":      gemini_advice,
    }
    if is_admin:
        result["model_name"]     = _MODEL_NAME
        result["model_accuracy"] = _MODEL_ACCURACY
    await _append_audit_db(db, user_uid=user["sub"], action_type="Prediction Run",
                           status="Success", detail=f"Predicted {req.subject}: {pct}% pass probability")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# GEMINI ENDPOINTS
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

    # Weakest assessment type
    if "ASSESSMENTTYPECODE" in df.columns:
        grp = df.groupby("ASSESSMENTTYPECODE")["MARKPERCENT"].mean()
        weakest = str(grp.idxmin()) if not grp.empty else "N/A"
    else:
        weakest = "N/A"

    # Previous trimester
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

    # Assessment breakdown
    breakdown = {}
    if "ASSESSMENTTYPECODE" in df.columns:
        for t, g in df.groupby("ASSESSMENTTYPECODE"):
            breakdown[str(t)] = {"avg_mark": round(float(g["MARKPERCENT"].mean()), 1),
                                 "count":    int(len(g))}

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


@app.post("/api/gemini/alert", tags=["Gemini"])
async def gemini_alert(req: GeminiAlertRequest, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
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
                           status="Success", detail=f"Gemini alert requested for {req.subject or 'all subjects'}")
    return {"alert": alert, "tokens_used": tokens}


@app.post("/api/gemini/analyse", tags=["Gemini"])
async def gemini_analyse(req: GeminiAnalyseRequest, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
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
                           status="Success", detail=f"Gemini analysis requested for {req.subject}")
    return {"analysis": analysis, "tokens_used": tokens, "model": "gemini-1.5-pro"}


@app.post("/api/gemini/ask", tags=["Gemini"])
async def gemini_ask(req: GeminiAskRequest, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stats = _subject_stats(req.subject, req.trimester, user)
    context = stats if stats else {"note": "No data loaded yet."}

    prompt = (
        f"You are an academic analyst for {req.subject or 'the institution'} at KOI. "
        f"Here is the current data: {context}. "
        f"Lecturer question: {req.question}. "
        "Answer in 2-3 sentences using the data provided. Be specific and actionable."
    )
    answer, tokens = await _gemini_call(_pro_model, prompt)
    await _append_audit_db(db, user_uid=user["sub"], action_type="AI Request",
                           status="Success", detail=f"Gemini question asked about {req.subject or 'institution'}")
    return {"answer": answer, "tokens_used": tokens, "model": "gemini-1.5-pro"}


# ─────────────────────────────────────────────────────────────────────────────
# AUTH EXTRAS — change password + logout
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/auth/change-password", tags=["Auth"])
async def change_password(
    req:  ChangePasswordRequest,
    user: dict = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
):
    email  = user.get("sub", "")
    result = await db.execute(select(UserModel).where(UserModel.email == email))
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
    email  = user.get("sub", "")
    result = await db.execute(select(UserModel).where(UserModel.email == email))
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
# SUBJECT ANALYTICS
# ─────────────────────────────────────────────────────────────────────────────

def _calc_subject_analytics(subject: str, trimester: Optional[str]) -> dict:
    if _DATA is None or "SUBJECTCODE" not in _DATA.columns:
        return {}

    df_all  = _DATA.dropna(subset=["MARKPERCENT"]).copy()
    df_subj = df_all[df_all["SUBJECTCODE"] == subject]
    if df_subj.empty:
        return {}

    df_scope = (df_subj[df_subj["STUDYPERIOD"] == trimester]
                if trimester and "STUDYPERIOD" in df_subj.columns else df_subj)
    df_inst  = (df_all[df_all["STUDYPERIOD"] == trimester]
                if trimester and "STUDYPERIOD" in df_all.columns  else df_all)
    if df_scope.empty:
        return {}

    avg_mark   = round(float(df_scope["MARKPERCENT"].mean()), 1)
    pass_rate  = round(float((df_scope["MARKPERCENT"] >= 50).mean() * 100), 1)
    fail_rate  = round(100.0 - pass_rate, 1)
    stu_count  = int(df_scope["STUDENTID_MASKED"].nunique()) if "STUDENTID_MASKED" in df_scope.columns else len(df_scope)
    inst_avg   = round(float(df_inst["MARKPERCENT"].mean()), 1)   if not df_inst.empty else avg_mark
    inst_pr    = round(float((df_inst["MARKPERCENT"] >= 50).mean() * 100), 1) if not df_inst.empty else pass_rate
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
        periods_w_data = [p for p in PERIODS_ORDER if "STUDYPERIOD" in df_subj.columns and p in df_subj["STUDYPERIOD"].values]
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
                pc = int(df_p["STUDENTID_MASKED"].nunique()) if "STUDENTID_MASKED" in df_p.columns else len(df_p)
                trimester_comparison.append({
                    "period":    p,
                    "avg":       round(float(df_p["MARKPERCENT"].mean()), 1),
                    "pass_rate": round(float((df_p["MARKPERCENT"] >= 50).mean() * 100), 1),
                    "count":     pc,
                })

    grade_distribution = []
    for band, lo, hi in GRADE_BANDS:
        s_cnt = int(((df_scope["MARKPERCENT"] >= lo) & (df_scope["MARKPERCENT"] <= hi)).sum())
        i_cnt = int(((df_inst["MARKPERCENT"]  >= lo) & (df_inst["MARKPERCENT"]  <= hi)).sum()) if not df_inst.empty else 0
        grade_distribution.append({"band": band, "subject_count": s_cnt, "institution_count": i_cnt})

    performance_trend = []
    if "STUDYPERIOD" in df_subj.columns:
        for p in PERIODS_ORDER:
            df_sp = df_subj[df_subj["STUDYPERIOD"] == p]
            df_ip = df_all[df_all["STUDYPERIOD"] == p]
            s_avg = round(float(df_sp["MARKPERCENT"].mean()), 1) if not df_sp.empty else None
            i_avg = round(float(df_ip["MARKPERCENT"].mean()), 1) if not df_ip.empty else None
            if s_avg is not None:
                performance_trend.append({"period": p, "subject_avg": s_avg, "institution_avg": i_avg})

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
    }


@app.get("/api/subjects/list", tags=["Subjects"])
async def subjects_list(user: dict = Depends(require_head_of_school)):
    if _DATA is None or "SUBJECTCODE" not in _DATA.columns:
        return []
    return sorted(_DATA["SUBJECTCODE"].dropna().unique().tolist())


@app.get("/api/subjects/analytics", tags=["Subjects"])
async def subjects_analytics(
    subject_a: str           = Query(...),
    subject_b: Optional[str] = Query(None),
    trimester: Optional[str] = Query(None),
    user: dict = Depends(require_head_of_school),
):
    stats_a = _calc_subject_analytics(subject_a, trimester)
    if not stats_a:
        raise HTTPException(404, f"No data found for subject {subject_a}")
    stats_b = _calc_subject_analytics(subject_b, trimester) if subject_b else None
    return {"subject_a": stats_a, "subject_b": stats_b}


# ─────────────────────────────────────────────────────────────────────────────
# INSTITUTION GEMINI ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

def _institution_stats() -> dict:
    if _DATA is None or _DATA.empty:
        return {}
    df = _DATA.dropna(subset=["MARKPERCENT"]).copy()
    if df.empty:
        return {}

    overall_avg  = round(float(df["MARKPERCENT"].mean()), 1)
    overall_pr   = round(float((df["MARKPERCENT"] >= 50).mean() * 100), 1)
    at_risk      = int((df["MARKPERCENT"] < 50).sum())
    countries    = int(df["COUNTRY_MASKED"].nunique()) if "COUNTRY_MASKED" in df.columns else 0

    latest = None
    if "STUDYPERIOD" in df.columns:
        for p in reversed(PERIODS_ORDER):
            if p in df["STUDYPERIOD"].values:
                latest = p
                break

    df_latest = df[df["STUDYPERIOD"] == latest] if latest and "STUDYPERIOD" in df.columns else df
    latest_pr = round(float((df_latest["MARKPERCENT"] >= 50).mean() * 100), 1) if not df_latest.empty else overall_pr

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
            intl.append({"country": str(country), "avg_mark": round(float(grp["MARKPERCENT"].mean()), 1)})
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


@app.post("/api/gemini/institution-alert", tags=["Gemini"])
async def gemini_institution_alert(user: dict = Depends(require_head_of_school), db: AsyncSession = Depends(get_db)):
    stats = _institution_stats()
    if not stats:
        return {"alert": "", "tokens_used": 0}
    subj_str = ", ".join(stats["subjects_below_50"][:5]) or "none"
    top3 = ", ".join(f"{s['subject']} ({s['pass_rate']}%)" for s in stats["top_3_failing"]) or "none"
    prompt = (
        f"Institution stats: overall pass rate {stats['latest_pass_rate']}% in period {stats['latest_period']}, "
        f"{stats['subjects_below_50_count']} subjects below 50%: {subj_str}. "
        f"Top failing: {top3}. "
        "Write ONE alert sentence for the Head of Technology. Name specific subjects. Be direct."
    )
    alert, tokens = await _gemini_call(_flash_model, prompt)
    await _append_audit_db(db, user_uid=user["sub"], action_type="AI Request",
                           status="Success", detail="Institution alert requested")
    return {"alert": alert, "tokens_used": tokens}


@app.post("/api/gemini/institution-analyse", tags=["Gemini"])
async def gemini_institution_analyse(user: dict = Depends(require_head_of_school), db: AsyncSession = Depends(get_db)):
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
async def gemini_institution_ask(req: GeminiInstitutionAskRequest, user: dict = Depends(require_head_of_school), db: AsyncSession = Depends(get_db)):
    stats = _institution_stats()
    context = stats if stats else {"note": "No data loaded yet."}
    prompt = (
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
    return {"data": list(reversed(_GEMINI_TOKEN_LOG)), "total": len(_GEMINI_TOKEN_LOG)}

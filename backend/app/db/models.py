"""
EDAPT v2 — SQLAlchemy ORM Models
Database: PostgreSQL
Project:  Educational Data Analytics and Predictive Tool (KOI)

Design notes:
  - snake_case column names are used throughout for Python idiom consistency;
    the originating CSV headers are noted in inline comments.
  - Every table carries created_at / updated_at audit timestamps.

This originally also had a full relational dimension/fact schema (Country,
Program, Trimester, Subject, ClassGroup, Lecturer, Student, Enrollment,
Assessment) for a planned CSV-to-SQL ETL that never happened — the app's
real serving path loads data directly from CSV into an in-memory dataframe
instead (see Prediction's own docstring below for the full story). Removed
during a codebase cleanup pass after confirming zero code anywhere queried,
wrote to, or imported those classes.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Shared declarative base for all EDAPT models."""
    __allow_unmapped__ = True


# ---------------------------------------------------------------------------
# Audit mixin — reusable created_at / updated_at on every table
# ---------------------------------------------------------------------------

class AuditMixin:
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)



# ===========================================================================
# ML OUTPUT TABLE
# ===========================================================================


class Prediction(AuditMixin, Base):
    """
    Stores ML model predictions for Mode 2 (Predictive).

    One row = one model's prediction for one student in one subject in one
    study period.

    NOTE ON IDENTIFIERS: this originally FK'd to Student.id/Trimester.id, but
    those tables (along with Subject/Enrollment/Assessment/ClassGroup/Program
    — since removed, see this module's docstring) were never populated — the
    app's real serving path loads data directly from the CSV into an
    in-memory dataframe, keyed by the raw string STUDENTID_MASKED/
    SUBJECTCODE/STUDYPERIOD values (e.g. "Student3340", "ICT205", "25.2"),
    not the integer IDs that schema assumed. Using those FKs would have
    required first building and maintaining a full CSV-to-SQL ETL, which
    nothing else in this codebase does. This table stores the same string
    identifiers the rest of the app actually uses, instead.

    Also originally had no subject reference at all (unique constraint was
    student+trimester+model_version) despite one student having a separate
    prediction per subject per period — added subject_code and fixed the
    unique constraint accordingly.
    """

    __tablename__ = "predictions"

    id: int = Column(BigInteger, primary_key=True, autoincrement=True)

    # Raw CSV-native identifiers — matches STUDENTID_MASKED/SUBJECTCODE/
    # STUDYPERIOD as used everywhere else in this app (roster endpoint,
    # /api/predict, subject_reliability.json), not an FK into the unused
    # Student/Trimester/Subject tables.
    student_id_masked: str = Column(String(50), nullable=False, index=True)
    subject_code:      str = Column(String(20), nullable=False, index=True)
    study_period:       str = Column(String(10), nullable=False, index=True)

    # Which model version served this prediction — the registry version id
    # (model_registry.py) for a complete-record prediction, or a
    # simulated-progress-model identifier for a mid-term estimate. Not an
    # arbitrary free-text tag: always traceable back to an actual saved
    # model package.
    model_version: str = Column(
        String(80),
        nullable=False,
        comment="Registry version id, or a simulated-progress model identifier",
    )

    # Primary binary prediction
    predicted_pass: bool = Column(
        Boolean,
        nullable=False,
        comment="True = model predicts Pass; False = model predicts Fail",
    )

    # Probability score from predict_proba (0.0 – 1.0)
    pass_probability: float | None = Column(
        Float,
        nullable=True,
        comment="Confidence score for Pass class from predict_proba (0.0–1.0)",
    )

    risk_band: str | None = Column(
        String(20),
        nullable=True,
        comment="Safe / At Risk / High Risk at prediction time",
    )

    # None for a complete-record prediction; "mid-term estimate" when served
    # by the simulated-progress model (predictor.predict_partial()).
    estimate_type: str | None = Column(
        String(30),
        nullable=True,
        comment="'mid-term estimate' for simulated-progress predictions, NULL for complete-record predictions",
    )

    # Ground-truth label — backfilled by reconcile_predictions.py once the
    # student-subject-period enrolment is fully graded (the same
    # per-enrolment clean check used everywhere else in this project, not a
    # fixed T3 2025 assumption).
    actual_pass: bool | None = Column(
        Boolean,
        nullable=True,
        comment="Backfilled once the enrolment is fully graded. NULL until then.",
    )
    reconciled_at: datetime | None = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When actual_pass was backfilled",
    )

    # True when actual_pass came from reconcile_predictions.py's resit
    # fallback (that student's LATEST attempt for this subject+period, used
    # only when no ATTEMPTNUMBER==1 record exists) rather than the standard
    # attempt-1 clean-enrolment check every other "clean" definition in this
    # project uses. Kept distinguishable rather than silently merged into one
    # actual_pass number — see reconcile_predictions.py's module docstring
    # for why these two reconciliation paths aren't guaranteed equivalent.
    reconciled_via_resit: bool = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="actual_pass came from a resit-fallback reconciliation, not the standard attempt-1 check",
    )

    # Natural-language insight generated by Gemini API for this prediction
    gemini_insight: str | None = Column(
        Text,
        nullable=True,
        comment="Gemini-generated NL explanation for this prediction (Mode 2 AI insight)",
    )

    predicted_at: datetime = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Timestamp when inference was run",
    )

    __table_args__ = (
        CheckConstraint(
            "pass_probability IS NULL OR (pass_probability >= 0.0 AND pass_probability <= 1.0)",
            name="ck_pass_probability_range",
        ),
        UniqueConstraint(
            "student_id_masked", "subject_code", "study_period", "model_version",
            name="uq_prediction_student_subject_period_model",
        ),
        Index("ix_prediction_subject_period_model", "subject_code", "study_period", "model_version"),
    )


class Intervention(Base):
    """A real action a lecturer or admin took for a student — an email sent, a
    meeting held, a referral to support services.

    Deliberately a separate table from `predictions` rather than columns on it.
    A prediction is a model output, immutable once written and upserted on
    re-prediction (see Prediction's unique constraint); an intervention is a
    human act that happened once and must never be overwritten by a later
    re-prediction of the same student. One student/subject/period can also
    accumulate several interventions over a term, which columns on a
    one-row-per-prediction table could not represent.

    Identifiers follow the same convention as Prediction: raw CSV-native
    STUDENTID_MASKED/SUBJECTCODE/STUDYPERIOD strings, not FKs into the unused
    Student/Subject tables. `prediction_id` IS a real FK, because predictions
    is a real, populated table — but it is nullable, since a lecturer may log
    an action without a specific prediction on screen.

    ON DELETE SET NULL rather than CASCADE: if a prediction row were ever
    deleted, the record that a human contacted a student must survive it. The
    intervention is the more important fact of the two.
    """

    __tablename__ = "interventions"

    id: int = Column(BigInteger, primary_key=True, autoincrement=True)

    student_id_masked: str = Column(String(50), nullable=False, index=True)
    subject_code:      str = Column(String(20), nullable=False, index=True)
    study_period:      str = Column(String(10), nullable=False, index=True)

    prediction_id: int | None = Column(
        BigInteger,
        ForeignKey("predictions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="The prediction this action responded to, when logged from one",
    )

    # Free text, but the UI offers a fixed set (see INTERVENTION_ACTION_TYPES
    # in main.py). Not a DB enum: adding a new action type should not require a
    # schema migration in a project with no migration framework — the app-level
    # whitelist is the real gate, and it is validated on write.
    action_type: str = Column(
        String(50),
        nullable=False,
        index=True,
        comment="e.g. email sent | meeting scheduled | referred to support services | other",
    )

    notes: str | None = Column(Text, nullable=True)

    created_by: str = Column(
        String(255),
        nullable=False,
        index=True,
        comment="Email/uid of the lecturer or admin who logged this action",
    )

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_intervention_student_subject_period",
              "student_id_masked", "subject_code", "study_period"),
    )


class RiskEmailTemplate(Base):
    """
    Singleton config row (always id=1) for the "Students at Risk" bulk
    action's email wording.

    This system has no real student email anywhere — STUDENTID_MASKED is a
    one-way pseudonym applied upstream, before the data ever reaches this
    project (see README's masking section). So this is never sent by the
    app itself: it's reference text a staff member copies into the real
    email they send on their own, to the real student they personally
    know, outside this system — the bulk action on the Students at Risk
    page then logs an `Intervention` row (action_type="email sent") per
    selected student to record that it happened. One fixed-id row rather
    than a generic key/value settings table: this is the one piece of
    admin-configurable free-text copy in the app, so there's no need for
    a table designed to hold more than that.
    """

    __tablename__ = "risk_email_templates"

    id: int = Column(Integer, primary_key=True, autoincrement=False)

    subject: str = Column(String(255), nullable=False)
    body:    str = Column(
        Text, nullable=False,
        comment="May contain {{student_id}}, {{subject_code}}, {{study_period}}, {{risk_band}} placeholders",
    )

    updated_by: str | None = Column(String(254), nullable=True)
    updated_at: datetime = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )


class OAuthProviderConfig(Base):
    """
    Per-provider Google/Microsoft sign-in configuration, editable from
    Settings > OAuth Providers instead of the GOOGLE_CLIENT_ID /
    MICROSOFT_CLIENT_ID / MICROSOFT_TENANT_ID environment variables this
    replaces — previously the one piece of app config that needed a
    redeploy to change.

    `provider` is a fixed primary key ("google"/"microsoft"); rows are
    seeded once at startup and never created/deleted through the API,
    since oauth_providers.py's verification functions only know how to
    handle these two providers. No client-secret column: this project only
    implements the ID-token flow (the frontend gets a signed ID token
    straight from Google/Microsoft's own JS SDK and hands it to us) rather
    than a server-side authorization-code exchange, so a secret is never
    needed — client_id is a public identifier, not sensitive, the same way
    it was already embedded directly in the frontend bundle before this.
    """

    __tablename__ = "oauth_provider_configs"

    provider:  str      = Column(String(20), primary_key=True)
    client_id: str      = Column(String(255), nullable=False, default="")
    tenant_id: str | None = Column(String(255), nullable=True, comment="Microsoft only; blank means 'common'")
    enabled:   bool     = Column(Boolean, nullable=False, default=False)

    updated_by: str | None = Column(String(254), nullable=True)
    updated_at: datetime = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )


class User(AuditMixin, Base):
    """
    Application user account for EDAPT staff / admins.

    No student PII is ever stored in this table — it only represents
    the system users who operate the analytics dashboard.
    """

    __tablename__ = "users"

    id: int = Column(Integer, primary_key=True, autoincrement=True)

    name: str = Column(String(120), nullable=False)

    email: str = Column(
        String(254),
        unique=True,
        nullable=False,
        index=True,
        comment="Login email address — must be unique across all accounts",
    )

    hashed_password: str = Column(
        String(255),
        nullable=False,
        comment="bcrypt hash of the user's password. Plain-text is never stored.",
    )

    role: str = Column(
        String(30),
        nullable=False,
        default="staff",
        comment="Role label: 'admin' or 'staff'",
    )

    is_active: bool = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Set to False to disable login without deleting the account",
    )

    is_super_admin: bool = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default='false',
        comment="True for the primary system administrator account — grants access to user management and audit log",
    )

    subjects: list = Column(
        JSON,
        nullable=True,
        default=list,
        comment="List of subject codes assigned to this lecturer (e.g. ['ICT104', 'ICT201'])",
    )


# ===========================================================================
# AUDIT LOG TABLE
# ===========================================================================


class PendingIngest(Base):
    """
    Shared, cross-worker store for the two-phase ingestion flow's
    analyze -> confirm handoff. Was an in-memory Python dict
    (_PENDING_INGESTS in main.py) — worked in the single-worker dev setup,
    but prod runs 4 gunicorn workers (docker-compose.prod.yml), each a
    separate OS process that doesn't share Python-level state. A
    non-sticky load balancer could route analyze and confirm to different
    workers, and confirm would never find the pending upload.

    Postgres, not Redis: this project already has Postgres wired in for
    everything else (users, audit_logs, predictions), and the actual
    requirement here — one row per in-flight upload, read once by
    confirm, with a short TTL — doesn't need Redis's speed or pub/sub;
    a plain table with a checked-at-read-time expiry (see
    PENDING_INGEST_TTL_MINUTES in main.py) is simpler to add correctly
    than introducing a whole new dependency this late for one use case.

    kind is the primary key (not id/token) to preserve the existing
    single-slot-per-file-type semantics: a new analyze() for the same
    kind overwrites the previous pending upload outright (upsert), the
    same "old token silently becomes invalid" protection the in-memory
    dict already had — verified in test_ingestion_e2e.py.
    """

    __tablename__ = "pending_ingests"

    kind: str = Column(String(20), primary_key=True, comment="'capstone' or 'attendance'")
    token: str = Column(String(36), nullable=False, comment="uuid4, must match the confirm call's token")
    filename: str | None = Column(String(255), nullable=True)
    csv_bytes: bytes = Column(LargeBinary, nullable=False, comment="Raw uploaded file content, re-parsed at confirm time")
    created_at: datetime = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IngestJob(Base):
    """
    Tracks one confirm-time ingestion run so it can happen in the background.

    Confirm used to block the HTTP request for as long as the actual
    parse/feature-build/merge/commit took — a real problem on a 200MB /
    2.5M-row attendance file, where that work can run well past any
    reasonable client timeout. Confirm now returns immediately with a job
    id, the real work runs after the response via FastAPI BackgroundTasks,
    and progress is exposed by polling this table instead of by holding the
    request open.

    A real table, not an in-memory dict — this project already learned that
    lesson once with PendingIngest: prod runs 4 gunicorn workers, so a status
    poll needs to see this row regardless of which worker actually ran the
    background task.
    """

    __tablename__ = "ingest_jobs"

    id: int = Column(Integer, primary_key=True, autoincrement=True)

    kind: str = Column(String(20), nullable=False, comment="'capstone' or 'attendance'")

    status: str = Column(
        String(20), nullable=False, default="running", server_default="running",
        comment="running | success | failed",
    )

    filename: str | None = Column(String(255), nullable=True)

    started_by: str = Column(
        String(254), nullable=False,
        comment="Email/uid of the admin who confirmed this ingestion",
    )

    started_at: datetime = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: datetime | None = Column(DateTime(timezone=True), nullable=True)

    result: dict | None = Column(
        JSON, nullable=True,
        comment="Same payload the old synchronous confirm endpoint returned, once finished successfully",
    )
    error_detail: str | None = Column(Text, nullable=True)


class AnalyzeJob(Base):
    """
    Tracks one analyze-time parse/classify run so it can happen in the
    background — the same fix IngestJob already applied to confirm, now
    applied to the earlier analyze step too.

    Analyze used to run entirely inline in the request: read the upload,
    parse it with pandas, classify its columns, and write the PendingIngest
    row, all before responding. A client disconnect partway through (a page
    refresh, a closed tab) could abort that request — and with it, the
    PendingIngest write — leaving nothing durable to resume from. Analyze
    now returns immediately with a job id, the real work runs via
    BackgroundTasks (unaffected by the client's connection once the
    response has been sent), and GET /api/ingest/{kind}/analyze-status
    lets a freshly-loaded page discover a still-running (or just-failed)
    analyze from before the refresh instead of looking blank.
    """

    __tablename__ = "analyze_jobs"

    id: int = Column(Integer, primary_key=True, autoincrement=True)

    kind: str = Column(String(20), nullable=False, comment="'capstone' or 'attendance'")

    status: str = Column(
        String(20), nullable=False, default="running", server_default="running",
        comment="running | success | failed",
    )

    filename: str | None = Column(String(255), nullable=True)

    started_by: str = Column(
        String(254), nullable=False,
        comment="Email/uid of the admin who uploaded this file",
    )

    started_at: datetime = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: datetime | None = Column(DateTime(timezone=True), nullable=True)

    result: dict | None = Column(
        JSON, nullable=True,
        comment="Same {token, row_count, columns, ...} payload the old synchronous analyze endpoint returned",
    )
    error_detail: str | None = Column(Text, nullable=True)


class AuditLog(Base):
    """
    Persistent audit trail for all significant system events.

    Replaces the previous in-memory _AUDIT_LOGS list so events survive
    server restarts and can be queried with filters.
    """

    __tablename__ = "audit_logs"

    id: int = Column(Integer, primary_key=True, autoincrement=True)

    timestamp = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    user_uid: str = Column(
        String(254),
        nullable=False,
        index=True,
        comment="Email / identifier of the acting user",
    )

    action_type: str = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Event category (e.g. Login, Data Upload, User Created)",
    )

    status: str = Column(
        String(20),
        nullable=False,
        comment="Outcome label: Success | Alert | Error",
    )

    detail: str | None = Column(
        Text,
        nullable=True,
        comment="Human-readable description of the event",
    )


# ===========================================================================
# API KEY TABLE
# ===========================================================================


class ApiKey(AuditMixin, Base):
    """
    Admin-issued credential for the external prediction endpoint
    (/api/v1/predict). Only a salted hash is ever stored — the raw key is
    returned once at creation time and cannot be recovered afterwards,
    mirroring User.hashed_password's "never store plaintext" convention.
    """

    __tablename__ = "api_keys"

    id: int = Column(Integer, primary_key=True, autoincrement=True)

    name: str = Column(
        String(120),
        nullable=False,
        comment="Admin-chosen label identifying what this key is for",
    )

    key_prefix: str = Column(
        String(20),
        nullable=False,
        comment="First few characters of the raw key, for display in the key list only",
    )

    hashed_key: str = Column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="sha256 hex digest of the raw key. Plain-text is never stored.",
    )

    created_by: str = Column(
        String(254),
        nullable=False,
        comment="Email of the Head of Technology admin who generated this key",
    )

    last_used_at: datetime | None = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Updated on every successful /api/v1/predict call using this key",
    )

    revoked: bool = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Soft-revoke flag — revoked keys are kept for audit history, not deleted",
    )

    revoked_at: datetime | None = Column(DateTime(timezone=True), nullable=True)

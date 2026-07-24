"""
EDAPT v2 — SQLAlchemy ORM Models
Database: PostgreSQL
Project:  Educational Data Analytics and Predictive Tool (KOI)

Design notes:
  - All student and country identity is stored ONLY as pre-masked integer IDs.
    No raw PII is ever ingested or stored.
  - Lookup/dimension tables (Country, Program, Subject, Trimester, Lecturer)
    are separated from fact tables (Enrollment, Assessment, Prediction) so that
    anonymised IDs can be joined without exposing underlying identity.
  - snake_case column names are used throughout for Python idiom consistency;
    the originating CSV headers are noted in inline comments.
  - Every table carries created_at / updated_at audit timestamps.
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
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, relationship


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
# DIMENSION / LOOKUP TABLES
# ===========================================================================


class Country(AuditMixin, Base):
    """
    Lookup table for anonymised country codes.

    COUNTRY_MASKED (integer) is the only identifier stored.
    The human-readable country name is optional and should only be
    populated if the dataset provider has approved its inclusion.
    """

    __tablename__ = "countries"

    id: int = Column(Integer, primary_key=True, autoincrement=True)

    # CSV source: COUNTRY_MASKED — pre-anonymised integer supplied in dataset
    country_masked_id: int = Column(
        Integer,
        unique=True,
        nullable=False,
        index=True,
        comment="Anonymised integer ID from source dataset (COUNTRY_MASKED)",
    )

    # Optional label — leave NULL unless de-identification policy permits it
    country_label: str | None = Column(
        String(100),
        nullable=True,
        comment="Human-readable label; populate only if permitted by privacy policy",
    )

    # Relationships
    students: list = relationship("Student", back_populates="country")


class Program(AuditMixin, Base):
    """
    Academic program / course (e.g. Bachelor of IT).

    CSV source: STUDYPACKAGE
    """

    __tablename__ = "programs"

    id: int = Column(Integer, primary_key=True, autoincrement=True)

    # CSV source: STUDYPACKAGE — raw code kept for traceability
    study_package_code: str = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Raw STUDYPACKAGE code from source dataset",
    )

    program_name: str | None = Column(
        String(200),
        nullable=True,
        comment="Human-readable program name (e.g. Bachelor of Information Technology)",
    )

    # Relationships
    enrollments: list = relationship("Enrollment", back_populates="program")


class Trimester(AuditMixin, Base):
    """
    Academic calendar period.

    CSV source: STUDYPERIOD — e.g. '2024T1', '2025T2'
    Stores both the raw string and decomposed year/trimester_number
    for easier time-series queries.
    """

    __tablename__ = "trimesters"

    id: int = Column(Integer, primary_key=True, autoincrement=True)

    # CSV source: STUDYPERIOD
    study_period_code: str = Column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
        comment="Raw STUDYPERIOD code from dataset (e.g. 2024T1)",
    )

    year: int = Column(
        SmallInteger,
        nullable=False,
        comment="Calendar year extracted from study period",
    )

    trimester_number: int = Column(
        SmallInteger,
        nullable=False,
        comment="Trimester within year (1, 2, or 3)",
    )

    is_prediction_target: bool = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="True for T3 2025 — the ML prediction target period",
    )

    __table_args__ = (
        CheckConstraint("trimester_number BETWEEN 1 AND 3", name="ck_trimester_number"),
        UniqueConstraint("year", "trimester_number", name="uq_trimester_year_number"),
    )

    # Relationships
    enrollments: list = relationship("Enrollment", back_populates="trimester")
    # No `predictions` relationship — Prediction stores study_period as a raw
    # string (see Prediction's docstring), not an FK to this table.


class Subject(AuditMixin, Base):
    """
    An individual unit / subject offered within a program.

    CSV source: SUBJECTCODE, CLASSGROUP
    """

    __tablename__ = "subjects"

    id: int = Column(Integer, primary_key=True, autoincrement=True)

    # CSV source: SUBJECTCODE
    subject_code: str = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="Raw SUBJECTCODE from dataset (e.g. KBS101)",
    )

    subject_name: str | None = Column(
        String(200),
        nullable=True,
        comment="Full subject name if available",
    )

    # Relationships
    class_groups: list = relationship("ClassGroup", back_populates="subject")


class ClassGroup(AuditMixin, Base):
    """
    A specific class/section of a subject in a given trimester.

    CSV source: CLASSGROUP — e.g. 'KBS101-A', 'KBS101-B'
    Normalised out of Subject so multiple parallel groups can be tracked.
    """

    __tablename__ = "class_groups"

    id: int = Column(Integer, primary_key=True, autoincrement=True)

    subject_id: int = Column(
        Integer,
        ForeignKey("subjects.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # CSV source: CLASSGROUP
    class_group_code: str = Column(
        String(50),
        nullable=False,
        comment="Raw CLASSGROUP code from dataset",
    )

    lecturer_id: int | None = Column(
        Integer,
        ForeignKey("lecturers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    __table_args__ = (
        UniqueConstraint("subject_id", "class_group_code", name="uq_classgroup_subject"),
    )

    # Relationships
    subject: "Subject" = relationship("Subject", back_populates="class_groups")
    lecturer: "Lecturer" = relationship("Lecturer", back_populates="class_groups")
    enrollments: list = relationship("Enrollment", back_populates="class_group")


class Lecturer(AuditMixin, Base):
    """
    Lecturer / teaching staff record.

    Not present in the original CSV columns but required per project spec.
    lecturer_masked_id follows the same anonymisation pattern as students.
    """

    __tablename__ = "lecturers"

    id: int = Column(Integer, primary_key=True, autoincrement=True)

    # Anonymised integer, analogous to STUDENTID_MASKED
    lecturer_masked_id: int = Column(
        Integer,
        unique=True,
        nullable=False,
        index=True,
        comment="Anonymised integer lecturer ID — no PII stored",
    )

    department: str | None = Column(
        String(100),
        nullable=True,
    )

    # Relationships
    class_groups: list = relationship("ClassGroup", back_populates="lecturer")


# ===========================================================================
# CORE ENTITY TABLE
# ===========================================================================


class Student(AuditMixin, Base):
    """
    Anonymised student record.

    IMPORTANT: Only the pre-masked integer ID (STUDENTID_MASKED) is stored.
    No name, email, DOB or any other PII is ever persisted here.
    Demographic attributes (gender, age group, country) are stored as
    low-granularity categorical values safe for analytics.
    """

    __tablename__ = "students"

    id: int = Column(Integer, primary_key=True, autoincrement=True)

    # CSV source: STUDENTID_MASKED — the sole student identifier
    student_masked_id: int = Column(
        Integer,
        unique=True,
        nullable=False,
        index=True,
        comment="Pre-anonymised integer ID from source dataset (STUDENTID_MASKED). No PII.",
    )

    # CSV source: GENDERCODE — categorical label (e.g. 'M', 'F', 'X', 'U')
    gender_code: str | None = Column(
        String(5),
        nullable=True,
        comment="Low-granularity gender category (GENDERCODE). Never a direct identifier.",
    )

    # CSV source: AGEGROUP — bucketed range (e.g. '18-24', '25-34')
    age_group: str | None = Column(
        String(20),
        nullable=True,
        comment="Age band (AGEGROUP). Bucketed to prevent re-identification.",
    )

    country_id: int | None = Column(
        Integer,
        ForeignKey("countries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    country: "Country" = relationship("Country", back_populates="students")
    enrollments: list = relationship("Enrollment", back_populates="student")
    # No `predictions` relationship — Prediction stores student_id_masked as a
    # raw string (see Prediction's docstring), not an FK to this table.

    __table_args__ = (
        Index("ix_student_gender_agegroup", "gender_code", "age_group"),
    )


# ===========================================================================
# FACT / TRANSACTION TABLES
# ===========================================================================


class Enrollment(AuditMixin, Base):
    """
    Junction / fact table linking a Student to a ClassGroup in a Trimester
    under a specific Program.

    One row = one student enrolled in one class group in one trimester.
    Assessment records hang off this enrollment.
    """

    __tablename__ = "enrollments"

    id: int = Column(BigInteger, primary_key=True, autoincrement=True)

    student_id: int = Column(
        Integer,
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    class_group_id: int = Column(
        Integer,
        ForeignKey("class_groups.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    trimester_id: int = Column(
        Integer,
        ForeignKey("trimesters.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    program_id: int = Column(
        Integer,
        ForeignKey("programs.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "student_id", "class_group_id", "trimester_id",
            name="uq_enrollment_student_classgroup_trimester",
        ),
        Index("ix_enrollment_trimester_program", "trimester_id", "program_id"),
    )

    # Relationships
    student: "Student" = relationship("Student", back_populates="enrollments")
    class_group: "ClassGroup" = relationship("ClassGroup", back_populates="enrollments")
    trimester: "Trimester" = relationship("Trimester", back_populates="enrollments")
    program: "Program" = relationship("Program", back_populates="enrollments")
    assessments: list = relationship("Assessment", back_populates="enrollment")


class Assessment(AuditMixin, Base):
    """
    Individual assessment submission record.

    One row = one attempt at one assessment item within an enrollment.

    CSV sources:
      ASSESSMENTID        → assessment_source_id
      ASSESSMENTTYPECODE  → assessment_type_code
      ATTEMPTNUMBER       → attempt_number
      ASSESSMENTMARK      → assessment_mark
      MAXMARK             → max_mark
      WEIGHTING           → weighting
      MARKPERCENT         → mark_percent  (derived in source; stored for traceability)
    """

    __tablename__ = "assessments"

    id: int = Column(BigInteger, primary_key=True, autoincrement=True)

    enrollment_id: int = Column(
        BigInteger,
        ForeignKey("enrollments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # CSV source: ASSESSMENTID — opaque identifier from source system
    assessment_source_id: str = Column(
        String(50),
        nullable=False,
        comment="Raw ASSESSMENTID from source dataset",
    )

    # CSV source: ASSESSMENTTYPECODE — e.g. 'EXAM', 'ASSIGN', 'QUIZ'
    assessment_type_code: str = Column(
        String(30),
        nullable=False,
        comment="Assessment category (ASSESSMENTTYPECODE)",
    )

    # CSV source: ATTEMPTNUMBER — 1 for first sit, 2+ for supplementary
    attempt_number: int = Column(
        SmallInteger,
        nullable=False,
        default=1,
        comment="Attempt number (ATTEMPTNUMBER); 1 = first attempt",
    )

    # CSV source: ASSESSMENTMARK — raw mark awarded
    assessment_mark: float | None = Column(
        Float,
        nullable=True,
        comment="Raw mark awarded (ASSESSMENTMARK). NULL = not yet submitted.",
    )

    # CSV source: MAXMARK — maximum possible mark for this item
    max_mark: float = Column(
        Float,
        nullable=False,
        comment="Maximum achievable mark (MAXMARK)",
    )

    # CSV source: WEIGHTING — contribution to final grade (0.0 – 1.0 or 0–100)
    weighting: float | None = Column(
        Float,
        nullable=True,
        comment="Assessment weighting toward final grade (WEIGHTING)",
    )

    # CSV source: MARKPERCENT — pre-calculated percentage; stored for auditability
    mark_percent: float | None = Column(
        Float,
        nullable=True,
        comment="Percentage score (MARKPERCENT). Derived field from source; kept for audit.",
    )

    __table_args__ = (
        CheckConstraint("attempt_number >= 1", name="ck_attempt_number_positive"),
        CheckConstraint("max_mark > 0", name="ck_max_mark_positive"),
        CheckConstraint(
            "assessment_mark IS NULL OR (assessment_mark >= 0 AND assessment_mark <= max_mark)",
            name="ck_assessment_mark_range",
        ),
        UniqueConstraint(
            "enrollment_id", "assessment_source_id", "attempt_number",
            name="uq_assessment_enrollment_source_attempt",
        ),
        Index("ix_assessment_type_attempt", "assessment_type_code", "attempt_number"),
    )

    # Relationships
    enrollment: "Enrollment" = relationship("Enrollment", back_populates="assessments")


# ===========================================================================
# ML OUTPUT TABLE
# ===========================================================================


class Prediction(AuditMixin, Base):
    """
    Stores ML model predictions for Mode 2 (Predictive).

    One row = one model's prediction for one student in one subject in one
    study period.

    NOTE ON IDENTIFIERS: this originally FK'd to Student.id/Trimester.id, but
    those tables (along with Subject/Enrollment/Assessment/ClassGroup/Program)
    are never populated — the app's real serving path loads data directly
    from the CSV into an in-memory dataframe, keyed by the raw string
    STUDENTID_MASKED/SUBJECTCODE/STUDYPERIOD values (e.g. "Student3340",
    "ICT205", "25.2"), not the integer IDs this schema assumed. Using those
    FKs would have required first building and maintaining a full CSV-to-SQL
    ETL into the unrelated relational schema below, which nothing else in
    this codebase does. This table stores the same string identifiers the
    rest of the app actually uses, instead.

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

"""
Import Base and all models here so Alembic's env.py can find them
via a single `from app.db.base import Base` import.
"""

from app.db.models import Base  # noqa: F401 — re-exported for Alembic
from app.db.models import User

# Import every model so SQLAlchemy registers them against the metadata
from app.db.models import (  # noqa: F401
    Assessment,
    ClassGroup,
    Country,
    Enrollment,
    Lecturer,
    Prediction,
    Program,
    Student,
    Subject,
    Trimester,
)

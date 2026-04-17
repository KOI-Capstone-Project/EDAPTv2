"""
EDAPT v2 — Application Configuration
Reads from environment variables / .env file via pydantic-settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://edapt_user:changeme@db:5432/edapt_v2"

    # App
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "info"
    SECRET_KEY: str = "change-me"

    # CORS — in dev allow the React dev server
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:80"]

    # Gemini
    GEMINI_API_KEY: str = ""

    # ── Auth ─────────────────────────────────────────────────────────────────
    # How long a JWT stays valid. 480 min = 8 hours (one work day).
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480


settings = Settings()

from __future__ import annotations

from pathlib import Path
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    ENV: str = Field(default="dev")
    TZ: str = Field(default="Asia/Seoul")

    DATABASE_URL: str = Field(
        ...,
        description="mysql+pymysql://user:password@host:3306/dbname?charset=utf8mb4",
    )

    STORAGE_DIR: str = Field(default=str(PROJECT_ROOT / "storage"))
    INTERVIEW_AUDIO_CLEANUP_INTERVAL_SEC: int = Field(default=1800)
    INTERVIEW_AUDIO_STALE_TTL_SEC: int = Field(default=86400)

    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = Field(default="gpt-4o-mini")
    OPENAI_STT_MODEL: str = Field(default="gpt-4o-mini-transcribe")
    OPENAI_STT_TIMEOUT_SEC: int = Field(default=60)

    # Business Policy Settings
    RESUME_MAX_UPLOAD_SIZE: int = Field(default=10 * 1024 * 1024)  # 10MB
    RESUME_DEFAULT_QUESTION_COUNT: int = Field(default=30)
    RESUME_QUESTION_CANDIDATE_COUNT: int = Field(default=50)
    INTERVIEW_PRACTICE_QUESTION_COUNT: int = Field(default=5)
    ANALYSIS_TIMEOUT_SEC: int = Field(default=180)
    WEAKNESS_REPORT_TIMEOUT_SEC: int = Field(default=180)

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> "Settings":
    return Settings()


settings = get_settings()

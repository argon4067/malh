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

    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = Field(default="gpt-4.1-mini")

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> "Settings":
    return Settings()


settings = get_settings()
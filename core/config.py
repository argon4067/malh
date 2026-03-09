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
    OPENAI_TRANSCRIPT_REFINE_MODEL: str | None = None
    OPENAI_TRANSCRIPT_REFINE_TIMEOUT_SEC: int = Field(default=12)
    FASTER_WHISPER_MODEL_SIZE: str = Field(default="small")
    FASTER_WHISPER_DEVICE: str = Field(default="cpu")
    FASTER_WHISPER_COMPUTE_TYPE: str = Field(default="int8")
    FASTER_WHISPER_BEAM_SIZE: int = Field(default=5)

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> "Settings":
    return Settings()


settings = get_settings()

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from pydantic import BeforeValidator, PostgresDsn, computed_field
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def parse_csv_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ValueError(value)


REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    SENTRY_DSN: str | None = None
    GIT_COMMIT: str | None = None
    SENTRY_TRACE_SAMPLE_RATE: float = 0.1
    SENTRY_PROFILE_SAMPLE_RATE: float = 0.1
    UVICORN_LOG_LEVEL: str = "INFO"
    API_V1_STR: str = "/api/v1"

    CORS_ALLOWED_ORIGINS: Annotated[
        list[str], NoDecode, BeforeValidator(parse_csv_list)
    ] = [
        "http://localhost:3000",
        "http://localhost:3001",
    ]
    API_KEY: str = ""

    POSTGRES_USER: str | None = None
    POSTGRES_PASSWORD: str = "changeme"
    POSTGRES_HOST: str | None = None
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str | None = None
    DB_CONNECTION_POOL_MAX_OVERFLOW: int = 100

    CELERY_DEFAULT_QUEUE: str = "transcribe"
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None
    CELERY_PREFETCH_MULTIPLIER: int = 1
    WHISPER_IMPLEMENTATION: str | None = None
    CONTAINER_API_KEY: str | None = None
    CONTAINER_ID: str | None = None

    MEILI_URL: str | None = None
    MEILI_MASTER_KEY: str | None = None
    MEILI_INDEX: str = "calls"
    MEILI_INDEX_SPLIT_BY_MONTH: bool = False
    TYPESENSE_URL: str | None = None
    TYPESENSE_API_KEY: str | None = None

    API_BASE_URL: str | None = None

    S3_ENDPOINT: str = "http://minio:9000"
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None
    S3_BUCKET: str | None = None
    S3_PUBLIC_URL: str = ""

    @computed_field
    @property
    def sqlalchemy_database_uri(self) -> str:
        return PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        ).unicode_string()

    @property
    def celery_gpu_queue(self) -> str:
        return f"{self.CELERY_DEFAULT_QUEUE}_gpu"

    @property
    def has_meilisearch(self) -> bool:
        return bool(self.MEILI_URL and self.MEILI_MASTER_KEY)

    @property
    def has_typesense(self) -> bool:
        return bool(self.TYPESENSE_URL and self.TYPESENSE_API_KEY)


def get_settings() -> Settings:
    return Settings()


class SettingsProxy:
    def __getattr__(self, name: str) -> Any:
        return getattr(get_settings(), name)


settings = SettingsProxy()

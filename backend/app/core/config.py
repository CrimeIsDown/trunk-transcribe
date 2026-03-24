from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from pydantic import BeforeValidator, PostgresDsn, computed_field
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

API_TRANSCRIPTION_IMPLEMENTATIONS = ("openai", "deepgram", "deepinfra")
SUPPORTED_TRANSCRIPTION_BACKENDS = ("whisper", "api", "qwen", "voxtral")
TRANSCRIPTION_QUEUE_BY_BACKEND = {
    "whisper": "transcribe_whisper",
    "api": "transcribe_api",
    "qwen": "transcribe_qwen",
    "voxtral": "transcribe_voxtral",
}
POST_TRANSCRIBE_QUEUE = "post_transcribe"


def parse_csv_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ValueError(value)


def validate_transcription_backend(value: str) -> str:
    if value not in SUPPORTED_TRANSCRIPTION_BACKENDS:
        supported = ", ".join(SUPPORTED_TRANSCRIPTION_BACKENDS)
        raise ValueError(
            f"Unsupported transcription backend {value!r}. Supported values: {supported}"
        )
    return value


def resolve_api_backend_for_implementation(
    backend: str, whisper_implementation: str | None = None
) -> str:
    implementation = whisper_implementation
    if implementation:
        implementation = implementation.partition(":")[0]
    if backend == "whisper" and implementation in API_TRANSCRIPTION_IMPLEMENTATIONS:
        return "api"
    return backend


def resolve_transcription_backend(
    explicit_backend: str | None,
    default_backend: str = "whisper",
    whisper_implementation: str | None = None,
) -> str:
    backend = explicit_backend or default_backend
    backend = resolve_api_backend_for_implementation(backend, whisper_implementation)
    return validate_transcription_backend(backend)


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
    CELERY_QUEUES: Annotated[list[str], NoDecode, BeforeValidator(parse_csv_list)] = []
    CELERY_PREFETCH_MULTIPLIER: int = 1
    DEFAULT_TRANSCRIPTION_BACKEND: str = "whisper"
    TRANSCRIPTION_BACKEND: str | None = None
    ASR_API_URL: str | None = None
    ASR_MODEL: str | None = None
    ASR_PROVIDER: str | None = None
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
    def resolved_default_transcription_backend(self) -> str:
        return resolve_transcription_backend(
            None,
            default_backend=self.DEFAULT_TRANSCRIPTION_BACKEND,
            whisper_implementation=self.WHISPER_IMPLEMENTATION,
        )

    @property
    def resolved_transcription_backend(self) -> str:
        return resolve_transcription_backend(
            self.TRANSCRIPTION_BACKEND,
            default_backend=self.resolved_default_transcription_backend,
            whisper_implementation=self.WHISPER_IMPLEMENTATION,
        )

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

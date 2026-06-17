import logging
import os
from threading import Lock

from celery_batches import Batches

from app.core.transcription_profiles import (
    DEFAULT_DEEPINFRA_BASE_URL,
    DEFAULT_OPENAI_BASE_URL,
    TranscriptionProfile,
    resolve_transcription_profile,
)
from app.task import Task
from .base import BaseWhisper


class TranscriptionTask(Task):
    _models: dict[str, BaseWhisper] = {}
    model_lock = Lock()

    def model(self, transcription_profile: str | None = None) -> BaseWhisper:
        self.validate_requested_profile(transcription_profile)
        worker_profile = self.worker_profile
        if worker_profile.canonical not in self._models:
            self._models[worker_profile.canonical] = self.initialize_model(
                worker_profile.canonical
            )
        return self._models[worker_profile.canonical]

    def resolve_profile(
        self, transcription_profile: str | None = None
    ) -> TranscriptionProfile:
        if transcription_profile is None:
            transcription_profile = self.default_profile
        return resolve_transcription_profile(
            explicit_profile=transcription_profile,
            default_profile=os.getenv("DEFAULT_TRANSCRIPTION_PROFILE"),
        )

    def resolve_provider_and_model(
        self, transcription_profile: str | None = None
    ) -> tuple[str, str]:
        self.validate_requested_profile(transcription_profile)
        profile = self.worker_profile
        return profile.provider, profile.model

    @property
    def default_profile(self) -> str:
        return self.worker_profile.canonical

    @property
    def worker_profile(self) -> TranscriptionProfile:
        return resolve_transcription_profile(
            explicit_profile=os.getenv("TRANSCRIPTION_PROFILE"),
            default_profile=os.getenv("DEFAULT_TRANSCRIPTION_PROFILE"),
        )

    def validate_requested_profile(self, transcription_profile: str | None = None) -> None:
        if transcription_profile is None:
            return

        requested_profile = self.resolve_profile(transcription_profile)
        worker_profile = self.worker_profile
        if requested_profile.model_key != worker_profile.model_key:
            raise RuntimeError(
                "Worker model_key mismatch: "
                f"task requested {requested_profile.model_key!r}, "
                f"worker is configured for {worker_profile.model_key!r}."
            )

    def initialize_model(self, transcription_profile: str) -> BaseWhisper:
        with self.model_lock:
            profile = self.resolve_profile(transcription_profile)
            if profile.kind == "vendor" and profile.provider == "cloudflare":
                from .cloudflare_ai import CloudflareAiWhisper

                return CloudflareAiWhisper(
                    base_url=self._get_profile_base_url(profile),
                    model=profile.model,
                    headers=self._get_profile_headers(profile),
                )

            from .whisper_asr_api import WhisperAsrApi

            headers = self._get_profile_headers(profile)
            base_url = self._get_profile_base_url(profile)
            logging.info(
                "Initializing ASR client kind=%s provider=%s model=%s base_url=%s endpoint_target=%s",
                profile.kind,
                profile.provider,
                profile.model,
                base_url,
                profile.endpoint_target,
            )
            return WhisperAsrApi(
                base_url=base_url,
                provider=profile.provider,
                model=profile.model,
                headers=headers,
            )

    def _get_profile_base_url(self, profile: TranscriptionProfile) -> str:
        if profile.kind == "vendor":
            if profile.provider == "openai":
                return os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL)
            if profile.provider == "deepinfra":
                return os.getenv("DEEPINFRA_BASE_URL", DEFAULT_DEEPINFRA_BASE_URL)
            if profile.provider == "cloudflare":
                if base_url := os.getenv("CLOUDFLARE_BASE_URL"):
                    return base_url
                account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
                if not account_id:
                    raise RuntimeError("CLOUDFLARE_ACCOUNT_ID env must be set.")
                return (
                    "https://api.cloudflare.com/client/v4/accounts/"
                    f"{account_id}/ai/run"
                )
            raise RuntimeError(f"Unsupported vendor provider {profile.provider}")

        if profile.platform == "vast":
            return (
                os.getenv("ASR_ROUTER_URL")
                or os.getenv("ASR_API_URL")
                or "http://asr-router:8001/v1"
            )

        return os.getenv("ASR_API_URL", "http://localhost:5000/v1")

    def _get_profile_headers(self, profile: TranscriptionProfile) -> dict[str, str]:
        headers: dict[str, str] = {}
        if profile.kind == "vendor":
            if profile.provider == "openai":
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    raise RuntimeError("OPENAI_API_KEY env must be set.")
                headers["Authorization"] = f"Bearer {api_key}"
                return headers
            if profile.provider == "deepinfra":
                api_key = os.getenv("DEEPINFRA_API_KEY")
                if not api_key:
                    raise RuntimeError("DEEPINFRA_API_KEY env must be set.")
                headers["Authorization"] = f"Bearer {api_key}"
                return headers
            if profile.provider == "cloudflare":
                api_key = os.getenv("CLOUDFLARE_API_TOKEN")
                if not api_key:
                    raise RuntimeError("CLOUDFLARE_API_TOKEN env must be set.")
                headers["Authorization"] = f"Bearer {api_key}"
                return headers
            raise RuntimeError(f"Unsupported vendor provider {profile.provider}")

        if profile.platform == "vast":
            headers["X-ASR-Endpoint-Target"] = profile.endpoint_target
        return headers


WhisperTask = TranscriptionTask


class WhisperBatchTask(Batches, TranscriptionTask):
    pass

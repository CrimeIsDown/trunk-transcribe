import logging
import os
from threading import Lock

from celery_batches import Batches

from app.core.config import (
    API_TRANSCRIPTION_IMPLEMENTATIONS,
    resolve_transcription_backend,
)
from app.task import Task
from .base import BaseWhisper

API_IMPLEMENTATIONS = list(API_TRANSCRIPTION_IMPLEMENTATIONS)
LOCAL_IMPLEMENTATIONS = ["whisper", "faster-whisper", "whispers2t", "whisper.cpp"]
OPENAI_COMPATIBLE_PROVIDER_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepinfra": "https://api.deepinfra.com/v1/openai",
}


class WhisperTask(Task):
    _models: dict[str, BaseWhisper] = {}
    model_lock = Lock()

    def model(self, implementation: str | None = None) -> BaseWhisper:
        if not implementation:
            implementation = self.default_implementation
        implementation = self.normalize_implementation(implementation)
        if implementation not in self._models:
            self._models[implementation] = self.initialize_model(implementation)
        return self._models[implementation]

    def normalize_implementation(self, implementation: str) -> str:
        name, _, model = implementation.partition(":")
        if name in API_IMPLEMENTATIONS:
            return f"whisper-asr-api:{name}:{model}"
        return implementation

    @property
    def default_implementation(self) -> str:
        backend = resolve_transcription_backend(
            os.getenv("TRANSCRIPTION_BACKEND"),
            default_backend=os.getenv("DEFAULT_TRANSCRIPTION_BACKEND", "whisper"),
            whisper_implementation=os.getenv("WHISPER_IMPLEMENTATION"),
        )

        if backend in {"qwen", "voxtral"}:
            provider_name = os.getenv("ASR_PROVIDER", backend)
            backend_model_name = os.getenv("ASR_MODEL", backend)
            return f"whisper-asr-api:{provider_name}:{backend_model_name}"

        if backend == "api":
            whisper_implementation = os.getenv("WHISPER_IMPLEMENTATION")
            if whisper_implementation not in API_IMPLEMENTATIONS:
                supported = ", ".join(API_IMPLEMENTATIONS)
                raise RuntimeError(
                    f"TRANSCRIPTION_BACKEND=api requires WHISPER_IMPLEMENTATION to be one of: {supported}"
                )

            api_model_name: str | None = os.getenv("WHISPER_MODEL")

            if whisper_implementation == "openai":
                api_model_name = "whisper-1"

            if whisper_implementation == "deepinfra" and not api_model_name:
                api_model_name = "openai/whisper-large-v3-turbo"

            return f"whisper-asr-api:{whisper_implementation}:{api_model_name}"

        whisper_implementation = os.getenv("WHISPER_IMPLEMENTATION", "whisper-asr-api")
        if whisper_implementation in LOCAL_IMPLEMENTATIONS:
            supported = ", ".join(API_IMPLEMENTATIONS + ["whisper-asr-api"])
            raise RuntimeError(
                f"Local Whisper implementations have been removed. Use one of: {supported}"
            )

        whisper_model_name: str | None = os.getenv("WHISPER_MODEL")

        if whisper_implementation == "openai":
            whisper_model_name = "whisper-1"

        if whisper_implementation == "deepinfra" and not whisper_model_name:
            whisper_model_name = "openai/whisper-large-v3-turbo"

        if whisper_implementation == "whisper-asr-api":
            provider_name = os.getenv("ASR_PROVIDER", "speaches")
            whisper_model_name = (
                os.getenv("ASR_MODEL")
                or whisper_model_name
                or "Systran/faster-distil-whisper-small.en"
            )
            return f"whisper-asr-api:{provider_name}:{whisper_model_name}"

        return f"{whisper_implementation}:{whisper_model_name}"

    def initialize_model(self, implementation: str) -> BaseWhisper:
        with self.model_lock:
            implementation = self.normalize_implementation(implementation)
            logging.info(f"Initializing whisper model {implementation}")
            implementation, _, model = implementation.partition(":")
            if implementation == "whisper-asr-api":
                from .whisper_asr_api import WhisperAsrApi

                provider_name = None
                model_name = None
                if model:
                    provider_name, _, model_name = model.partition(":")
                headers = self._get_provider_headers(provider_name)
                base_url = self._get_provider_base_url(provider_name)
                return WhisperAsrApi(
                    base_url=base_url,
                    provider=provider_name or os.getenv("ASR_PROVIDER"),
                    model=model_name
                    or os.getenv("ASR_MODEL")
                    or os.getenv("WHISPER_MODEL"),
                    headers=headers,
                )

            if implementation in LOCAL_IMPLEMENTATIONS:
                raise RuntimeError(
                    f"Local Whisper implementation {implementation} is no longer supported"
                )

            raise RuntimeError(f"Unknown implementation {implementation}")

    def _get_provider_base_url(self, provider_name: str | None) -> str:
        if provider_name == "openai":
            return os.getenv(
                "OPENAI_BASE_URL",
                os.getenv(
                    "ASR_API_URL", OPENAI_COMPATIBLE_PROVIDER_BASE_URLS["openai"]
                ),
            )
        if provider_name == "deepinfra":
            return os.getenv(
                "DEEPINFRA_BASE_URL",
                os.getenv(
                    "ASR_API_URL", OPENAI_COMPATIBLE_PROVIDER_BASE_URLS["deepinfra"]
                ),
            )
        return os.getenv("ASR_API_URL", "http://localhost:5000/v1")

    def _get_provider_headers(self, provider_name: str | None) -> dict[str, str]:
        if provider_name == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY env must be set.")
            return {"Authorization": f"Bearer {api_key}"}
        if provider_name == "deepinfra":
            api_key = os.getenv("DEEPINFRA_API_KEY")
            if not api_key:
                raise RuntimeError("DEEPINFRA_API_KEY env must be set.")
            return {"Authorization": f"Bearer {api_key}"}
        return {}


class WhisperBatchTask(Batches, WhisperTask):
    pass

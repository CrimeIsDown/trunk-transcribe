import logging
import os
from threading import Lock

from celery_batches import Batches

from app.core.config import API_TRANSCRIPTION_IMPLEMENTATIONS, resolve_transcription_backend
from app.task import Task
from .base import BaseWhisper

API_IMPLEMENTATIONS = list(API_TRANSCRIPTION_IMPLEMENTATIONS)
LOCAL_IMPLEMENTATIONS = ["whisper", "faster-whisper", "whispers2t", "whisper.cpp"]


class WhisperTask(Task):
    _models: dict[str, BaseWhisper] = {}
    model_lock = Lock()

    def model(self, implementation: str | None = None) -> BaseWhisper:
        if not implementation:
            implementation = self.default_implementation
        if implementation not in self._models:
            self._models[implementation] = self.initialize_model(implementation)
        return self._models[implementation]

    @property
    def default_implementation(self) -> str:
        backend = resolve_transcription_backend(
            os.getenv("TRANSCRIPTION_BACKEND"),
            default_backend=os.getenv("DEFAULT_TRANSCRIPTION_BACKEND", "whisper"),
            whisper_implementation=os.getenv("WHISPER_IMPLEMENTATION"),
        )

        if backend in {"qwen", "voxtral"}:
            provider_name = os.getenv("ASR_PROVIDER", backend)
            model_name = os.getenv("ASR_MODEL", backend)
            return f"whisper-asr-api:{provider_name}:{model_name}"

        if backend == "api":
            whisper_implementation = os.getenv("WHISPER_IMPLEMENTATION")
            if whisper_implementation not in API_IMPLEMENTATIONS:
                supported = ", ".join(API_IMPLEMENTATIONS)
                raise RuntimeError(
                    f"TRANSCRIPTION_BACKEND=api requires WHISPER_IMPLEMENTATION to be one of: {supported}"
                )

            model_name = os.getenv("WHISPER_MODEL")

            if whisper_implementation == "openai":
                model_name = "whisper-1"

            if whisper_implementation == "deepgram" and not model_name:
                model_name = "nova-2"

            if whisper_implementation == "deepinfra" and not model_name:
                model_name = "openai/whisper-large-v3-turbo"

            return f"{whisper_implementation}:{model_name}"

        whisper_implementation = os.getenv("WHISPER_IMPLEMENTATION", "whisper-asr-api")
        if whisper_implementation in LOCAL_IMPLEMENTATIONS:
            supported = ", ".join(API_IMPLEMENTATIONS + ["whisper-asr-api"])
            raise RuntimeError(
                f"Local Whisper implementations have been removed. Use one of: {supported}"
            )

        model_name = os.getenv("WHISPER_MODEL")

        if whisper_implementation == "openai":
            model_name = "whisper-1"

        if whisper_implementation == "deepgram" and not model_name:
            model_name = "nova-2"

        if whisper_implementation == "deepinfra" and not model_name:
            model_name = "openai/whisper-large-v3-turbo"

        if whisper_implementation == "whisper-asr-api":
            provider_name = os.getenv("ASR_PROVIDER", "whisper-asr-webservice")
            model_name = os.getenv("ASR_MODEL") or model_name or "small.en"
            return f"whisper-asr-api:{provider_name}:{model_name}"

        return f"{whisper_implementation}:{model_name}"

    def initialize_model(self, implementation: str) -> BaseWhisper:
        with self.model_lock:
            logging.info(f"Initializing whisper model {implementation}")
            implementation, _, model = implementation.partition(":")
            if implementation == "openai":
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    raise RuntimeError("OPENAI_API_KEY env must be set.")
                from .openai import OpenAIApi

                return OpenAIApi(api_key)
            if implementation == "deepgram":
                api_key = os.getenv("DEEPGRAM_API_KEY")
                if not api_key:
                    raise RuntimeError("DEEPGRAM_API_KEY env must be set.")
                from .deepgram import DeepgramApi

                return DeepgramApi(api_key, model)
            if implementation == "deepinfra":
                api_key = os.getenv("DEEPINFRA_API_KEY")
                if not api_key:
                    raise RuntimeError("DEEPINFRA_API_KEY env must be set.")
                from .deepinfra import DeepInfraApi

                return DeepInfraApi(api_key, model)
            if implementation == "whisper-asr-api":
                from .whisper_asr_api import WhisperAsrApi

                provider_name = None
                model_name = None
                if model:
                    provider_name, _, model_name = model.partition(":")
                return WhisperAsrApi(
                    base_url=os.getenv("ASR_API_URL", "http://localhost:5000"),
                    provider=provider_name or os.getenv("ASR_PROVIDER"),
                    model=model_name or os.getenv("ASR_MODEL") or os.getenv("WHISPER_MODEL"),
                )

            if implementation in LOCAL_IMPLEMENTATIONS:
                raise RuntimeError(
                    f"Local Whisper implementation {implementation} is no longer supported"
                )

            raise RuntimeError(f"Unknown implementation {implementation}")


class WhisperBatchTask(Batches, WhisperTask):
    pass

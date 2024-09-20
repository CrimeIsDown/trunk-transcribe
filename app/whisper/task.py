import logging
import os
from threading import Lock

from celery_batches import Batches

from .exceptions import WhisperException
from app.task import Task
from .base import BaseWhisper

API_IMPLEMENTATIONS = ["openai", "deepgram"]


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
        whisper_implementation = os.getenv("WHISPER_IMPLEMENTATION")
        if not whisper_implementation:
            raise WhisperException("WHISPER_IMPLEMENTATION env must be set.")

        model_name = os.getenv("WHISPER_MODEL")

        if whisper_implementation == "openai":
            model_name = "whisper-1"

        if whisper_implementation == "deepgram" and not model_name:
            model_name = "nova-2"

        return f"{whisper_implementation}:{model_name}"

    def initialize_model(self, implementation: str) -> BaseWhisper:
        with self.model_lock:
            logging.info(f"Initializing whisper model {implementation}")
            implementation, model = implementation.split(":", 1)
            if implementation == "whisper.cpp":
                from .whisper_cpp import WhisperCpp

                return WhisperCpp(
                    model,
                    os.getenv("WHISPERCPP_MODEL_DIR", "/usr/local/lib/whisper-models"),
                )
            if implementation == "faster-whisper":
                from .faster_whisper import FasterWhisper

                return FasterWhisper(model)
            if implementation == "whispers2t":
                from .whisper_s2t import WhisperS2T

                return WhisperS2T(model)
            if implementation == "whisper":
                from .whisper import Whisper

                return Whisper(model)
            if implementation == "openai":
                if not os.getenv("OPENAI_API_KEY"):
                    raise WhisperException("OPENAI_API_KEY env must be set.")
                from .openai import OpenAIApi

                return OpenAIApi(os.getenv("OPENAI_API_KEY", ""))
            if implementation == "deepgram":
                if not os.getenv("DEEPGRAM_API_KEY"):
                    raise WhisperException("DEEPGRAM_API_KEY env must be set.")
                from .deepgram import DeepgramApi

                return DeepgramApi(os.getenv("DEEPGRAM_API_KEY", ""), model)

            raise WhisperException(f"Unknown implementation {implementation}")


class WhisperBatchTask(Batches, WhisperTask):
    pass

import os
from threading import Lock

import whisper
from celery import Task

from app.config import get_ttl_hash, get_whisper_config


class WhisperTask(Task):
    _model = None
    model_lock = Lock()

    @property
    def model(self):
        with self.model_lock:
            if self._model is None:
                model_name = os.getenv("WHISPER_MODEL")
                if not isinstance(model_name, str):
                    raise RuntimeError("WHISPER_MODEL env must be set")
                self._model = whisper.load_model(model_name)
            return self._model


def transcribe(
    model: whisper.Whisper, model_lock: Lock, audio_file: str, initial_prompt: str = ""
) -> dict:
    whisper_kwargs = get_whisper_config(get_ttl_hash(cache_seconds=60))
    with model_lock:
        return model.transcribe(
            audio_file, language="en", initial_prompt=initial_prompt, **whisper_kwargs
        )

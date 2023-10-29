import json
import logging
import os
import subprocess
from csv import DictReader
from threading import Lock

import openai

import app.db as db
from app.config import get_ttl_hash, get_whisper_config
from app.task import Task


class WhisperTask(Task):
    _db_conn_pool = None
    _model = None
    model_lock = Lock()

    @property
    def db_conn_pool(self):
        if not self._db_conn_pool:
            self._db_conn_pool = db.create_pool()
        return self._db_conn_pool

    @property
    def model(self):
        with self.model_lock:
            if self._model is not None:
                return self._model

            model_name = os.getenv("WHISPER_MODEL")
            if model_name:
                if os.getenv("WHISPERCPP"):
                    self._model = WhisperCpp(model_name, os.getenv("WHISPERCPP"))
                elif os.getenv("FASTERWHISPER"):
                    self._model = FasterWhisper(model_name)
                else:
                    self._model = Whisper(model_name)
            else:
                if os.getenv("OPENAI_API_KEY"):
                    self._model = WhisperApi()
                else:
                    raise RuntimeError("WHISPER_MODEL env must be set")

            return self._model


class Whisper:
    def __init__(self, model_name):
        import whisper

        self.model = whisper.load_model(model_name)

    def transcribe(
        self,
        audio: str,
        language: str = "en",
        initial_prompt: str | None = None,
        **decode_options,
    ) -> dict:
        return self.model.transcribe(
            audio=audio,
            language=language,
            initial_prompt=initial_prompt,
            **decode_options,
        )


class FasterWhisper:
    vad_filter = False

    def __init__(self, model_name):
        if "cpu" in os.getenv("DESIRED_CUDA", ""):
            device = "cpu"
            compute_type = "int8"
        else:
            device = "cuda"
            compute_type = "float16"

        from faster_whisper import WhisperModel

        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)

        if os.getenv("FASTER_WHISPER_VAD_FILTER"):
            self.vad_filter = True

    def transcribe(
        self,
        audio: str,
        language: str = "en",
        initial_prompt: str | None = None,
        **decode_options,
    ):
        segments, _ = self.model.transcribe(
            audio=audio,
            language=language,
            initial_prompt=initial_prompt,
            vad_filter=self.vad_filter,
            **decode_options,
        )
        segments = list(segments)  # The transcription will actually run here.

        result = {
            "segments": [],
            "text": None,
        }
        if len(segments):
            result["segments"] = [dict(segment._asdict()) for segment in segments]
            result["text"] = "\n".join(
                [segment["text"] for segment in result["segments"]]
            )
        return result


class WhisperCpp:
    def __init__(self, model_name, model_dir):
        model_path = f"{model_dir}/ggml-{model_name}.bin"
        if os.path.isfile(model_path):
            self.model_path = model_path

    def transcribe(
        self,
        audio: str,
        language: str = "en",
        initial_prompt: str | None = None,
        **decode_options,
    ):
        args = [
            "whisper-cpp",
            "--model",
            self.model_path,
            "--language",
            language,
            "--output-csv",
        ]

        if initial_prompt:
            args += ["--prompt", initial_prompt]

        if "best_of" in decode_options and decode_options["best_of"]:
            args += ["--best-of", str(decode_options["best_of"])]

        if "beam_size" in decode_options and decode_options["beam_size"]:
            args += ["--beam-size", str(decode_options["beam_size"])]

        args.append(audio)

        p = subprocess.run(args)
        p.check_returncode()

        result = {"segments": [], "text": None}

        with open(f"{audio}.csv", newline="") as csvfile:
            transcript = DictReader(csvfile)
            for line in transcript:
                # Handle quirks of whisper.cpp
                if (
                    len(line["text"])
                    and "[BLANK_AUDIO]" not in line["text"]
                    and "[SOUND]" not in line["text"]
                ):
                    result["segments"].append(
                        {
                            "start": float(line["start"]) / 1000,
                            "end": float(line["end"]) / 1000,
                            "text": line["text"],
                        }
                    )

        if len(result["segments"]):
            result["text"] = "\n".join(
                [segment["text"] for segment in result["segments"]]
            )

        return result


class WhisperApi:
    openai = None

    def __init__(self):
        openai.api_key = os.getenv("OPENAI_API_KEY")

    def transcribe(
        self,
        audio: str,
        language: str = "en",
        initial_prompt: str | None = None,
        **decode_options,
    ):
        audio_file = open(audio, "rb")
        prompt = "This is a police radio dispatch transcript."
        if initial_prompt:
            prompt += "The following words may appear: " + initial_prompt
        return openai.Audio.transcribe(
            model="whisper-1",
            file=audio_file,
            prompt=initial_prompt,
            response_format="verbose_json",
            language=language,
        )


def transcribe(
    model,
    model_lock: Lock,
    audio_file: str,
    initial_prompt: str = "",
) -> dict:
    whisper_kwargs = get_whisper_config(get_ttl_hash(cache_seconds=60))
    # TODO: Remove the lock if we are using Whisper.cpp
    with model_lock:
        result = model.transcribe(
            audio_file, language="en", initial_prompt=initial_prompt, **whisper_kwargs
        )
        logging.debug("Transcription result: " + json.dumps(result, indent=4))
        return result

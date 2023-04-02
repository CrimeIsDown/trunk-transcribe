import json
import logging
import os
import subprocess
from threading import Lock

import openai

from app.config import get_ttl_hash, get_whisper_config
from app.task import Task


class WhisperTask(Task):
    _model = None
    model_lock = Lock()

    @property
    def model(self):
        with self.model_lock:
            if self._model is None:
                if os.getenv("OPENAI_API_KEY"):
                    self._model = WhisperApi()
                else:
                    model_name = os.getenv("WHISPER_MODEL")
                    if not isinstance(model_name, str):
                        raise RuntimeError("WHISPER_MODEL env must be set")
                    if os.getenv("WHISPERCPP"):
                        self._model = WhisperCpp(model_name, os.getenv("WHISPERCPP"))
                    else:
                        import whisper

                        self._model = whisper.load_model(model_name)
            return self._model


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
        ]

        if initial_prompt:
            args += ["--prompt", initial_prompt]

        if decode_options["best_of"]:
            args += ["--best-of", str(decode_options["best_of"])]

        if decode_options["beam_size"]:
            args += ["--beam-size", str(decode_options["beam_size"])]

        args.append(audio)

        p = subprocess.run(args, capture_output=True)
        p.check_returncode()

        output = p.stdout.decode("utf-8").splitlines()

        result = {"segments": [], "text": None}

        for line in output:
            if line.startswith("[") and " --> " in line:
                segment = line[line.find("]") + 1 :].strip().replace(">> ", "")
                # Handle quirks of whisper.cpp
                if (
                    len(segment)
                    and "[BLANK_AUDIO]" not in segment
                    and "[SOUND]" not in segment
                ):
                    result["segments"].append({"text": segment})

        if len(result["segments"]):
            result["text"] = " ".join(
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

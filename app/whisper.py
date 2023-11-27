from abc import ABC, abstractmethod
import json
import logging
import os
import subprocess
from csv import DictReader
from threading import Lock

from .config import get_ttl_hash, get_whisper_config
from .task import Task


class BaseWhisper(ABC):
    @abstractmethod
    def transcribe(
        self,
        audio: str,
        language: str = "en",
        initial_prompt: str | None = None,
        **decode_options,
    ) -> dict:
        pass


class WhisperTask(Task):
    _models = {}
    model_lock = Lock()

    def model(self, implementation: str | None = None):
        if not implementation:
            implementation = self.default_implementation
        if implementation not in self._models:
            self._models[implementation] = self.initialize_model(implementation)
        return self._models[implementation]

    @property
    def default_implementation(self) -> str:
        model_name = os.getenv("WHISPER_MODEL")
        if model_name:
            if os.getenv("WHISPERCPP"):
                return f"whisper.cpp:{model_name}"
            if os.getenv("FASTERWHISPER"):
                return f"faster-whisper:{model_name}"
            if os.getenv("DISTILWHISPER"):
                return f"distil-whisper:{model_name}"
            return f"whisper:{model_name}"

        if os.getenv("OPENAI_API_KEY"):
            return "openai:whisper-1"

        raise RuntimeError("WHISPER_MODEL env or OPENAI_API_KEY env must be set")

    def initialize_model(self, implementation: str) -> BaseWhisper:
        with self.model_lock:
            model_class, model = implementation.split(":", 1)
            if model_class == "whisper.cpp":
                return WhisperCpp(
                    model,
                    os.getenv("WHISPERCPP_MODEL_DIR", "/usr/local/lib/whisper-models"),
                )
            if model_class == "faster-whisper":
                return FasterWhisper(model)
            if model_class == "distil-whisper":
                return DistilWhisper(model)
            if model_class == "whisper":
                return Whisper(model)
            if model_class == "openai":
                return WhisperApi(os.getenv("OPENAI_API_KEY", ""))

            raise RuntimeError(f"Unknown implementation {implementation}")


class Whisper(BaseWhisper):
    def __init__(self, model_name: str):
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


class DistilWhisper(BaseWhisper):
    def __init__(self, model_name: str):
        import torch
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32

        model_id = f"distil-whisper/distil-{model_name}"

        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            model_id,
            torch_dtype=torch_dtype,
            low_cpu_mem_usage=True,
            use_safetensors=True,
        )
        model.to(device)

        processor = AutoProcessor.from_pretrained(model_id)

        self.pipe = pipeline(
            "automatic-speech-recognition",
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            max_new_tokens=128,
            chunk_length_s=15,
            batch_size=16,
            torch_dtype=torch_dtype,
            device=device,
        )

    def transcribe(
        self,
        audio: str,
        language: str = "en",
        initial_prompt: str | None = None,
        **decode_options,
    ) -> dict:
        output = self.pipe(audio, return_timestamps=True)
        result = {
            "segments": [],
            "text": output["text"],  # type: ignore
        }
        for chunk in output["chunks"]:  # type: ignore
            result["segments"].append(
                {
                    "start": chunk["timestamp"][0],
                    "end": chunk["timestamp"][1],
                    "text": chunk["text"],
                }
            )
        return result


class FasterWhisper(BaseWhisper):
    vad_filter = False

    def __init__(self, model_name: str):
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
    ) -> dict:
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


class WhisperCpp(BaseWhisper):
    def __init__(self, model_name: str, model_dir: str):
        model_path = f"{model_dir}/ggml-{model_name}.bin"
        if os.path.isfile(model_path):
            self.model_path = model_path

    def transcribe(
        self,
        audio: str,
        language: str = "en",
        initial_prompt: str | None = None,
        **decode_options,
    ) -> dict:
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
        os.unlink(f"{audio}.csv")

        if len(result["segments"]):
            result["text"] = "\n".join(
                [segment["text"] for segment in result["segments"]]
            )

        return result


class WhisperApi(BaseWhisper):
    def __init__(self, api_key: str):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key)

    def transcribe(
        self,
        audio: str,
        language: str = "en",
        initial_prompt: str | None = None,
        **decode_options,
    ) -> dict:
        audio_file = open(audio, "rb")
        prompt = os.getenv(
            "OPENAI_PROMPT", "This is a police radio dispatch transcript."
        )
        if initial_prompt:
            prompt += "The following words may appear: " + initial_prompt
        return self.client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            prompt=prompt,
            response_format="verbose_json",
            language=language,
        ).model_dump()


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
        os.unlink(audio_file)
        logging.debug(
            f"{audio_file} transcription result: " + json.dumps(result, indent=4)
        )
        return result

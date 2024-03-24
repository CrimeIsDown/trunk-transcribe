from abc import ABC, abstractmethod
import json
import logging
import os
import subprocess
from csv import DictReader
from threading import Lock
import time
from typing_extensions import Optional, TypedDict

from .config import get_transcript_cleanup_config, get_ttl_hash, get_whisper_config
from .task import Task


class WhisperSegment(TypedDict):
    start: float
    end: float
    text: str


class WhisperResult(TypedDict):
    text: str
    segments: list[WhisperSegment]
    language: Optional[str]


class BaseWhisper(ABC):
    @abstractmethod
    def transcribe(
        self,
        audio: str,
        language: str = "en",
        initial_prompt: str | None = None,
        **decode_options,
    ) -> WhisperResult:
        pass


class WhisperTask(Task):
    _models = {}
    model_lock = Lock()

    def model(self, implementation: str | None = None) -> BaseWhisper:
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
            if os.getenv("INSANELYFASTWHISPER"):
                return f"insanely-fast-whisper:{model_name}"
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
            if model_class == "insanely-fast-whisper":
                return InsanelyFastWhisper(model)
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
    ) -> WhisperResult:
        return self.model.transcribe(
            audio=audio,
            language=language,
            initial_prompt=initial_prompt,
            **decode_options,
        )


class InsanelyFastWhisper(BaseWhisper):
    def __init__(self, model_name: str):
        import torch
        from transformers import pipeline
        from transformers.utils import is_flash_attn_2_available

        device = os.getenv(
            "TORCH_DEVICE", "cuda:0" if torch.cuda.is_available() else "cpu"
        )
        torch_dtype = os.getenv("TORCH_DTYPE", torch.float16)

        model_id = f"openai/whisper-{model_name}"

        self.pipe = pipeline(
            "automatic-speech-recognition",
            model=model_id,
            torch_dtype=torch_dtype,
            device=device,
            model_kwargs={"attn_implementation": "flash_attention_2"}
            if is_flash_attn_2_available()
            else {"attn_implementation": "sdpa"},
        )

        if device == "mps":
            torch.mps.empty_cache()

    def transcribe(
        self,
        audio: str,
        language: str = "en",
        initial_prompt: str | None = None,
        **decode_options,
    ) -> WhisperResult:
        output = self.pipe(
            audio, chunk_length_s=30, batch_size=24, return_timestamps=True
        )
        result: WhisperResult = {
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
        import torch
        from faster_whisper import WhisperModel

        device = os.getenv(
            "TORCH_DEVICE", "cuda:0" if torch.cuda.is_available() else "cpu"
        )
        compute_type = os.getenv("TORCH_DTYPE", "int8" if "cpu" in os.getenv("TORCH_DEVICE", "") else "float16")

        self.model = WhisperModel(model_name, device=device, compute_type=compute_type)

        if os.getenv("FASTER_WHISPER_VAD_FILTER"):
            self.vad_filter = True

    def transcribe(
        self,
        audio: str,
        language: str = "en",
        initial_prompt: str | None = None,
        **decode_options,
    ) -> WhisperResult:
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
    ) -> WhisperResult:
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
    ) -> WhisperResult:
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
        ).model_dump()  # type: ignore


def cleanup_transcript(result: WhisperResult) -> WhisperResult:
    config = get_transcript_cleanup_config()

    indices_to_delete = set()

    hallucination_count = 0
    # Check for patterns to replace or delete
    for i, segment in enumerate(result["segments"]):
        for item in config:
            if item["match_type"] == "partial":
                is_match = item["pattern"].lower() in segment["text"].lower().strip()
            elif item["match_type"] == "full":
                is_match = item["pattern"].lower() == segment["text"].lower().strip()
            else:
                raise Exception("Unsupported match_type in config")

            if is_match:
                if item["is_hallucination"]:
                    hallucination_count += 1
                if item["action"] == "delete":
                    indices_to_delete.add(i)
                elif item["action"] == "replace":
                    if item["match_type"] == "partial":
                        segment["text"] = segment["text"].replace(
                            item["pattern"], item["replacement"]
                        )
                    elif item["match_type"] == "full":
                        segment["text"] = item["replacement"]
                break
    # Do not proceed any further if the entire transcript appears to be hallucinations
    if len(result["segments"]) == hallucination_count:
        raise RuntimeError("Transcript invalid, 100% hallucination")

    prev_seg_text = ""
    times_seg_repeated = 0
    # Check for repeated segments
    for i, segment in enumerate(result["segments"]):
        if prev_seg_text == segment["text"]:
            times_seg_repeated += 1
            # Delete all the repetitive segments (except for the first instance)
            # until we find a non-repetitive one or we reach the end of the file
            if times_seg_repeated == 2:
                for j in range(i - times_seg_repeated, i):
                    indices_to_delete.add(j)
            elif times_seg_repeated > 2:
                indices_to_delete.add(i)
        else:
            times_seg_repeated = 0
            prev_seg_text = segment["text"]

    # Delete the invalid segments from the transcript
    valid_segments = [
        segment
        for i, segment in enumerate(result["segments"])
        if i not in indices_to_delete
    ]

    result["segments"] = valid_segments
    result["text"] = "\n".join([segment["text"] for segment in valid_segments])

    return result


def transcribe(
    model,
    model_lock: Lock,
    audio_file: str,
    initial_prompt: str = "",
    cleanup: bool = False,
) -> WhisperResult:
    whisper_kwargs = get_whisper_config(get_ttl_hash(cache_seconds=60))
    # TODO: Remove the lock if we are using Whisper.cpp
    with model_lock:
        # measure transcription time
        start_time = time.time()

        result = model.transcribe(
            audio_file, language="en", initial_prompt=initial_prompt, **whisper_kwargs
        )
        os.unlink(audio_file)
        logging.debug(
            f"{audio_file} transcription result: " + json.dumps(result, indent=4)
        )

        end_time = time.time()
        execution_time = end_time - start_time
        logging.debug(f"Transcription execution time: {execution_time} seconds")

        return cleanup_transcript(result) if cleanup else result

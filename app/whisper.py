from abc import ABC, abstractmethod
import json
import logging
import os
import signal
import subprocess
from csv import DictReader
import sys
from threading import Lock
import time
from celery_batches import Batches
import sentry_sdk
from typing_extensions import Optional, List, TypedDict

from .exceptions import WhisperException
from .config import get_transcript_cleanup_config, get_ttl_hash, get_whisper_config
from .task import Task


class WhisperSegment(TypedDict):
    start: float
    end: float
    text: str


class WhisperResult(TypedDict):
    text: str
    segments: List[WhisperSegment]
    language: Optional[str]


class BaseWhisper(ABC):
    @abstractmethod
    def transcribe(
        self,
        audio: str,
        language: str = "en",
        initial_prompt: str | None = None,
        vad_filter: bool = False,
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
            implementation, model = implementation.split(":", 1)
            if implementation == "whisper.cpp":
                return WhisperCpp(
                    model,
                    os.getenv("WHISPERCPP_MODEL_DIR", "/usr/local/lib/whisper-models"),
                )
            if implementation == "faster-whisper":
                return FasterWhisper(model)
            if implementation == "whispers2t":
                return WhisperS2T(model)
            if implementation == "whisper":
                return Whisper(model)
            if implementation == "openai":
                if not os.getenv("OPENAI_API_KEY"):
                    raise WhisperException("OPENAI_API_KEY env must be set.")
                return WhisperApi(os.getenv("OPENAI_API_KEY", ""))
            if implementation == "deepgram":
                if not os.getenv("DEEPGRAM_API_KEY"):
                    raise WhisperException("DEEPGRAM_API_KEY env must be set.")
                return DeepgramApi(os.getenv("DEEPGRAM_API_KEY", ""), model)

            raise WhisperException(f"Unknown implementation {implementation}")


class WhisperBatchTask(Batches, WhisperTask):
    pass


class Whisper(BaseWhisper):
    def __init__(self, model_name: str):
        import whisper

        self.model = whisper.load_model(model_name)

    def transcribe(
        self,
        audio: str,
        language: str = "en",
        initial_prompt: str | None = None,
        vad_filter: bool = False,
        **decode_options,
    ) -> WhisperResult:
        return self.model.transcribe(
            audio=audio,
            language=language,
            initial_prompt=initial_prompt,
            **decode_options,
        )


class WhisperS2T(BaseWhisper):
    def __init__(self, model_name: str):
        import torch
        import whisper_s2t
        from whisper_s2t.backends.ctranslate2.model import BEST_ASR_CONFIG

        torch_device = os.getenv(
            "TORCH_DEVICE", "cuda:0" if torch.cuda.is_available() else "cpu"
        )
        device = torch_device.split(":")[0]
        device_index = torch_device.split(":")[1] if ":" in torch_device else "0"
        device_index = (
            [int(i) for i in device_index.split(",")]
            if "," in device_index
            else int(device_index)
        )
        compute_type = os.getenv(
            "TORCH_DTYPE",
            "int8" if "cpu" in os.getenv("TORCH_DEVICE", "") else "float16",
        )

        model_kwargs = {
            "asr_options": BEST_ASR_CONFIG,
            "device": device,
            "device_index": device_index,
            "compute_type": compute_type,
        }
        backend = "CTranslate2"
        self.model = whisper_s2t.load_model(
            model_identifier=model_name, backend=backend, **model_kwargs
        )

    def transcribe(
        self,
        audio: str,
        language: str = "en",
        initial_prompt: str | None = None,
        vad_filter: bool = False,
        **decode_options,
    ) -> WhisperResult:
        method = self.model.transcribe
        if vad_filter:
            method = self.model.transcribe_with_vad
        output = method(
            [audio],
            lang_codes=[language],
            tasks=["transcribe"],
            initial_prompts=[initial_prompt],
            batch_size=16,
        )
        result: WhisperResult = {
            "segments": [],
            "text": "",
            "language": language,
        }
        for chunk in output[0]:  # type: ignore
            result["segments"].append(
                {
                    "start": chunk["start_time"],
                    "end": chunk["end_time"],
                    "text": chunk["text"],
                }
            )
            result["text"] += chunk["text"] + "\n"
        return result

    def transcribe_bulk(
        self,
        audio_files: list[str],
        lang_codes: list[str] = [],
        initial_prompts: list[str] = [],
        vad_filter: bool = False,
        **decode_options,
    ) -> list[WhisperResult]:
        method = self.model.transcribe
        if vad_filter:
            method = self.model.transcribe_with_vad
        if not lang_codes:
            lang_codes = ["en" for _ in audio_files]
        output = method(
            audio_files,
            lang_codes=lang_codes,
            tasks=["transcribe" for _ in audio_files],
            initial_prompts=(
                initial_prompts if initial_prompts else [None for _ in audio_files]
            ),
            batch_size=16,
        )
        results: list[WhisperResult] = []

        for i, item in enumerate(output):
            result: WhisperResult = {
                "segments": [],
                "text": "",
                "language": lang_codes[i],
            }
            for chunk in item:  # type: ignore
                result["segments"].append(
                    {
                        "start": chunk["start_time"],
                        "end": chunk["end_time"],
                        "text": chunk["text"],
                    }
                )
                result["text"] += chunk["text"] + "\n"
            results.append(result)

        return results


class FasterWhisper(BaseWhisper):
    def __init__(self, model_name: str):
        import torch
        from faster_whisper import WhisperModel

        torch_device = os.getenv(
            "TORCH_DEVICE", "cuda:0" if torch.cuda.is_available() else "cpu"
        )
        device = torch_device.split(":")[0]
        device_index = torch_device.split(":")[1] if ":" in torch_device else "0"
        device_index = (
            [int(i) for i in device_index.split(",")]
            if "," in device_index
            else int(device_index)
        )
        compute_type = os.getenv(
            "TORCH_DTYPE",
            "int8" if "cpu" in os.getenv("TORCH_DEVICE", "") else "float16",
        )

        self.model = WhisperModel(
            model_name,
            device=device,
            device_index=device_index,
            compute_type=compute_type,
        )

        if os.getenv("FASTER_WHISPER_VAD_FILTER"):
            self.vad_filter = True

    def transcribe(
        self,
        audio: str,
        language: str = "en",
        initial_prompt: str | None = None,
        vad_filter: bool = False,
        **decode_options,
    ) -> WhisperResult:
        segments, _ = self.model.transcribe(
            audio=audio,
            language=language,
            initial_prompt=initial_prompt,
            vad_filter=vad_filter,
            **decode_options,
        )
        segments = list(segments)  # The transcription will actually run here.

        result = {"segments": [], "text": None, "language": language}
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
        vad_filter: bool = False,
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

        result: WhisperResult = {"segments": [], "text": "", "language": language}

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
        vad_filter: bool = False,
        **decode_options,
    ) -> WhisperResult:
        audio_file = open(audio, "rb")
        prompt = os.getenv(
            "OPENAI_PROMPT", "This is a police radio dispatch transcript."
        )
        if initial_prompt:
            prompt += " The following words may appear: " + initial_prompt
        return self.client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            prompt=prompt,
            response_format="verbose_json",
            language=language,
        ).model_dump()  # type: ignore


class DeepgramApi(BaseWhisper):
    def __init__(self, api_key: str, model: str = "nova-2"):
        from deepgram import DeepgramClient

        self.client = DeepgramClient(api_key=api_key)
        self.model = model

    def transcribe(
        self,
        audio: str,
        language: str = "en",
        initial_prompt: str | None = None,
        vad_filter: bool = False,
        **decode_options,
    ) -> WhisperResult:
        from deepgram import FileSource, PrerecordedOptions, PrerecordedResponse

        with open(audio, "rb") as audio_file:
            payload: FileSource = {"buffer": audio_file.read()}

        options = PrerecordedOptions(
            model=self.model,
            utterances=True,
            smart_format=True,
            language=language,
            keywords=initial_prompt,
        )
        response: PrerecordedResponse = self.client.listen.prerecorded.v(
            "1"
        ).transcribe_file(payload, options, timeout=120)

        if (
            response.results
            and response.results.utterances
            and response.results.channels
        ):
            return {
                "segments": [
                    {"start": u.start, "end": u.end, "text": u.transcript}
                    for u in response.results.utterances
                ],
                "text": response.results.channels[0].alternatives[0].transcript,
                "language": language,
            }
        return {"segments": [], "text": "", "language": language}


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
        raise WhisperException("Transcript invalid, 100% hallucination")

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
    model: BaseWhisper,
    model_lock: Lock,
    audio_file: str,
    initial_prompt: str = "",
    cleanup: bool = False,
    vad_filter: bool = False,
) -> WhisperResult:
    whisper_kwargs = get_whisper_config(get_ttl_hash(cache_seconds=60))
    # TODO: Remove the lock if we are using Whisper.cpp
    with model_lock:
        # measure transcription time
        start_time = time.time()

        try:
            result = model.transcribe(
                audio_file,
                language="en",
                initial_prompt=initial_prompt,
                vad_filter=vad_filter,
                **whisper_kwargs,
            )
        finally:
            os.unlink(audio_file)
        logging.debug(
            f"{audio_file} transcription result: " + json.dumps(result, indent=4)
        )

        end_time = time.time()
        execution_time = end_time - start_time
        logging.debug(f"Transcription execution time: {execution_time} seconds")

        return cleanup_transcript(result) if cleanup else result


def transcribe_bulk(
    model: WhisperS2T,
    model_lock: Lock,
    audio_files: list[str],
    initial_prompts: list[str] = [],
    cleanup: bool = False,
    vad_filter: bool = False,
) -> list[Optional[WhisperResult]]:
    whisper_kwargs = get_whisper_config(get_ttl_hash(cache_seconds=60))
    # TODO: Remove the lock if we are using Whisper.cpp
    with model_lock:
        # measure transcription time
        start_time = time.time()

        try:
            results = model.transcribe_bulk(
                audio_files=audio_files,
                initial_prompts=initial_prompts,
                vad_filter=vad_filter,
                **whisper_kwargs,
            )
        finally:
            for audio_file in audio_files:
                os.unlink(audio_file)
        logging.debug(
            f"{audio_files} transcription result: " + json.dumps(results, indent=4)
        )

        end_time = time.time()
        execution_time = end_time - start_time
        logging.debug(f"Transcription execution time: {execution_time} seconds")

        if cleanup:
            cleaned_results = []
            for result in results:
                try:
                    cleaned_results.append(cleanup_transcript(result))
                except WhisperException:
                    cleaned_results.append(None)
            return cleaned_results
        return results  # type: ignore


def handle_exception(e: Exception):
    if "CUDA error:" in str(e) or "CUDA out of memory" in str(e):
        logging.exception(e)
        sentry_sdk.capture_exception(e)
        # Exit the worker process to avoid further errors by triggering Docker to automatically restart the worker
        os.kill(
            os.getppid(),
            signal.SIGQUIT if hasattr(signal, "SIGQUIT") else signal.SIGTERM,
        )

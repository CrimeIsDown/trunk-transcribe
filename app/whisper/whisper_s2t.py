import os
from typing import Any

import torch
import whisper_s2t
from whisper_s2t.backends.ctranslate2.model import BEST_ASR_CONFIG

from .base import BaseWhisper, WhisperResult


class WhisperS2T(BaseWhisper):
    def __init__(self, model_name: str):
        torch_device = os.getenv(
            "TORCH_DEVICE", "cuda:0" if torch.cuda.is_available() else "cpu"
        )
        device = torch_device.split(":")[0]
        device_index = torch_device.split(":")[1] if ":" in torch_device else "0"
        device_index = (
            [int(i) for i in device_index.split(",")]  # type: ignore
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
        **decode_options: dict[Any, Any],
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
        for chunk in output[0]:
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
        **decode_options: dict[Any, Any],
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
                initial_prompts if initial_prompts else [""] * len(audio_files)
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
            for chunk in item:
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

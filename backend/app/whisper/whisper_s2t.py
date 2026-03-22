import os

import whisper_s2t
from whisper_s2t.backends.ctranslate2.model import BEST_ASR_CONFIG

from .base import BaseWhisper, TranscribeOptions, WhisperResult


class WhisperS2T(BaseWhisper):
    def __init__(self, model_name: str):
        torch_device = os.getenv(
            "TORCH_DEVICE", "cpu" if os.getenv("CUDA_VERSION") == "cpu" else "cuda:0"
        )
        device = torch_device.split(":")[0]
        device_index = torch_device.split(":")[1] if ":" in torch_device else "0"
        compute_type = os.getenv(
            "TORCH_DTYPE",
            "int8" if "cpu" in os.getenv("TORCH_DEVICE", "") else "float16",
        )

        model_kwargs = {
            "asr_options": BEST_ASR_CONFIG,
            "device": device,
            "device_index": (
                [int(i) for i in device_index.split(",")]
                if "," in device_index
                else int(device_index)
            ),
            "compute_type": compute_type,
        }
        backend = "CTranslate2"
        self.model = whisper_s2t.load_model(
            model_identifier=model_name, backend=backend, **model_kwargs
        )

    def transcribe(
        self,
        audio: str,
        options: TranscribeOptions,
        language: str = "en",
    ) -> WhisperResult:
        method = self.model.transcribe
        if options["vad_filter"]:
            method = self.model.transcribe_with_vad
        output = method(
            [audio],
            lang_codes=[language],
            tasks=["transcribe"],
            initial_prompts=[options["initial_prompt"]],
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
        options_list: list[TranscribeOptions],
        lang_codes: list[str] = [],
        vad_filter: bool = False,
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
            initial_prompts=[options["initial_prompt"] for options in options_list],
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

import os
import torch
from .base import BaseWhisper, WhisperResult
from faster_whisper import WhisperModel


class FasterWhisper(BaseWhisper):
    def __init__(self, model_name: str):
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

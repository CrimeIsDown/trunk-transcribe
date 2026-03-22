import os
from .base import BaseWhisper, TranscribeOptions, WhisperResult
from faster_whisper import WhisperModel


class FasterWhisper(BaseWhisper):
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

        self.model = WhisperModel(
            model_name,
            device=device,
            device_index=(
                [int(i) for i in device_index.split(",")]
                if "," in device_index
                else int(device_index)
            ),
            compute_type=compute_type,
        )

    def transcribe(
        self,
        audio: str,
        options: TranscribeOptions,
        language: str = "en",
    ) -> WhisperResult:
        segments, _ = self.model.transcribe(
            audio=audio,
            language=language,
            initial_prompt=options["initial_prompt"],
            vad_filter=options["vad_filter"],
            **options["decode_options"],
        )
        segments = list(segments)  # The transcription will actually run here.

        result: WhisperResult = {"segments": [], "text": "", "language": language}
        if len(segments):
            result["segments"] = [dict(segment._asdict()) for segment in segments]  # type: ignore
            result["text"] = "\n".join(
                [segment["text"] for segment in result["segments"]]
            )
        return result

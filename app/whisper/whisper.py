import whisper

from .base import BaseWhisper, TranscribeOptions, WhisperResult


class Whisper(BaseWhisper):
    def __init__(self, model_name: str):
        self.model = whisper.load_model(model_name)

    def transcribe(
        self,
        audio: str,
        options: TranscribeOptions,
        language: str = "en",
    ) -> WhisperResult:
        return self.model.transcribe(
            audio=audio,
            language=language,
            initial_prompt=options["initial_prompt"],
            **options["decode_options"],
        )

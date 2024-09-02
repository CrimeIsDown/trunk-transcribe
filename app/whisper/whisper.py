from .base import BaseWhisper, WhisperResult


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

import os
from openai import OpenAI

from .base import BaseWhisper, TranscribeOptions, WhisperResult


class OpenAIApi(BaseWhisper):
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)

    def transcribe(
        self,
        audio: str,
        options: TranscribeOptions,
        language: str = "en",
    ) -> WhisperResult:
        audio_file = open(audio, "rb")
        prompt = os.getenv(
            "OPENAI_PROMPT", "This is a police radio dispatch transcript."
        )
        if options["initial_prompt"]:
            prompt += " The following words may appear: " + options["initial_prompt"]
        return self.client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            prompt=prompt,
            response_format="verbose_json",
            language=language,
        ).model_dump()  # type: ignore

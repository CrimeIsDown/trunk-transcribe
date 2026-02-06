import os

from openai import OpenAI

from .base import BaseWhisper, TranscribeOptions, WhisperResult


class DeepInfraApi(BaseWhisper):
    def __init__(self, api_key: str, model: str):
        base_url = os.getenv(
            "DEEPINFRA_BASE_URL", "https://api.deepinfra.com/v1/openai"
        )
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def transcribe(
        self,
        audio: str,
        options: TranscribeOptions,
        language: str = "en",
    ) -> WhisperResult:
        with open(audio, "rb") as audio_file:
            prompt = os.getenv(
                "OPENAI_PROMPT", "This is a police radio dispatch transcript."
            )
            if options["initial_prompt"]:
                prompt += (
                    " The following words may appear: " + options["initial_prompt"]
                )
            return self.client.audio.transcriptions.create(
                model=self.model,
                file=audio_file,
                prompt=prompt,
                response_format="verbose_json",
                language=language,
            ).model_dump()  # type: ignore

import requests
from .base import BaseWhisper, WhisperResult


class WhisperAsrApi(BaseWhisper):
    def __init__(self, base_url: str):
        self.client = requests.Session()
        self.base_url = base_url

    def transcribe(
        self,
        audio: str,
        language: str = "en",
        initial_prompt: str | None = None,
        vad_filter: bool = False,
    ) -> WhisperResult:
        response = self.client.post(
            f"{self.base_url}/asr",
            files={"audio_file": open(audio, "rb")},
            params={
                "encode": "true",
                "task": "transcribe",
                "language": language,
                "initial_prompt": initial_prompt if initial_prompt is not None else "",
                "vad_filter": "true" if vad_filter else "false",
                "word_timestamps": "false",
                "output": "json",
            },
        )
        response.raise_for_status()
        return response.json()

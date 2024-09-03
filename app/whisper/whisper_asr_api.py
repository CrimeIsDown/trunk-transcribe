import os
import requests
from .base import BaseWhisper, WhisperResult


class WhisperAsrApi(BaseWhisper):
    def __init__(self):
        self.client = requests.Session()
        self.base_url = os.getenv("ASR_API_URL", "http://whisper:9000")

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
                "encode": True,
                "task": "transcribe",
                "language": language,
                "initial_prompt": initial_prompt,
                "vad_filter": vad_filter,
                "word_timestamps": False,
                "output": "json",
            },
        )
        response.raise_for_status()
        return response.json()

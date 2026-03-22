import requests
from .base import BaseWhisper, TranscribeOptions, WhisperResult


class WhisperAsrApi(BaseWhisper):
    def __init__(self, base_url: str):
        self.client = requests.Session()
        self.base_url = base_url

    def transcribe(
        self,
        audio: str,
        options: TranscribeOptions,
        language: str = "en",
    ) -> WhisperResult:
        response = self.client.post(
            f"{self.base_url}/asr",
            files={"audio_file": open(audio, "rb")},
            params={
                "encode": "true",
                "task": "transcribe",
                "language": language,
                "initial_prompt": options["initial_prompt"]
                if options["initial_prompt"] is not None
                else "",
                "vad_filter": "true" if options["vad_filter"] else "false",
                "word_timestamps": "false",
                "output": "json",
            },
            timeout=120,
        )
        response.raise_for_status()
        return response.json()

from __future__ import annotations

import requests
from .base import BaseWhisper, TranscribeOptions, WhisperResult


class WhisperAsrApi(BaseWhisper):
    def __init__(
        self,
        base_url: str,
        model: str | None = None,
        provider: str | None = None,
    ):
        self.client = requests.Session()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.provider = provider

    def _normalize_response(self, response_data: dict, language: str) -> WhisperResult:
        return {
            "text": response_data.get("text", ""),
            "segments": response_data.get("segments", []),
            "language": response_data.get("language", language),
        }

    def transcribe(
        self,
        audio: str,
        options: TranscribeOptions,
        language: str = "en",
    ) -> WhisperResult:
        with open(audio, "rb") as audio_file:
            if self.base_url.endswith("/v1"):
                response = self.client.post(
                    f"{self.base_url}/audio/transcriptions",
                    files={"file": audio_file},
                    data={
                        "model": self.model or "whisper-1",
                        "language": language,
                        "prompt": options["initial_prompt"] or "",
                        "response_format": "verbose_json",
                    },
                    timeout=120,
                )
            else:
                params = {
                    "encode": "true",
                    "task": "transcribe",
                    "language": language,
                    "initial_prompt": options["initial_prompt"]
                    if options["initial_prompt"] is not None
                    else "",
                    "vad_filter": "true" if options["vad_filter"] else "false",
                    "word_timestamps": "false",
                    "output": "json",
                }
                if self.provider:
                    params["provider"] = self.provider
                if self.model:
                    params["model"] = self.model

                response = self.client.post(
                    f"{self.base_url}/asr",
                    files={"audio_file": audio_file},
                    params=params,
                    timeout=120,
                )
        response.raise_for_status()
        return self._normalize_response(response.json(), language)

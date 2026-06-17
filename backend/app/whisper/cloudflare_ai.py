from __future__ import annotations

import base64

import requests

from .base import BaseWhisper, TranscribeOptions, WhisperResult


class CloudflareAiWhisper(BaseWhisper):
    def __init__(
        self,
        base_url: str,
        model: str,
        headers: dict[str, str] | None = None,
    ):
        self.client = requests.Session()
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.headers = headers or {}

    def _normalize_response(self, response_data: dict, language: str) -> WhisperResult:
        result = response_data.get("result", response_data)
        segments = result.get("segments") or []
        if not segments and result.get("text"):
            segments = [
                {"start": float(i), "end": float(i + 1), "text": line}
                for i, line in enumerate(
                    [line.strip() for line in result["text"].splitlines() if line.strip()]
                )
            ]
        return {
            "text": result.get("text", ""),
            "segments": segments,
            "language": result.get("language", language),
        }

    def transcribe(
        self,
        audio: str,
        options: TranscribeOptions,
        language: str = "en",
    ) -> WhisperResult:
        with open(audio, "rb") as audio_file:
            audio_base64 = base64.b64encode(audio_file.read()).decode("utf-8")

        payload = {
            "audio": audio_base64,
            "language": language,
            "task": "transcribe",
            "initial_prompt": options["initial_prompt"] or "",
        }
        payload.update(options.get("decode_options") or {})
        if options.get("vad_filter"):
            payload["vad_filter"] = True

        response = self.client.post(
            f"{self.base_url}/{self.model}",
            json=payload,
            headers=self.headers,
            timeout=120,
        )
        response.raise_for_status()
        return self._normalize_response(response.json(), language)

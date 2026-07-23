import os
from typing import Any

from openai import OpenAI

from .base import BaseWhisper, TranscribeOptions, WhisperResult, WhisperSegment


class OpenAIApi(BaseWhisper):
    def __init__(self, api_key: str, model: str = "whisper-1"):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    @property
    def is_diarization_model(self) -> bool:
        return self.model.startswith("gpt-4o-transcribe-diarize")

    @property
    def response_format(self) -> str:
        if self.model == "whisper-1":
            return "verbose_json"
        if self.is_diarization_model:
            return "diarized_json"
        return "json"

    @staticmethod
    def normalize_response(response: Any, language: str) -> WhisperResult:
        if isinstance(response, str):
            response_data: dict[str, Any] = {"text": response}
        elif isinstance(response, dict):
            response_data = response
        else:
            response_data = response.model_dump()

        text = response_data.get("text") or ""
        segments: list[WhisperSegment] = []
        for raw_segment in response_data.get("segments") or []:
            if not isinstance(raw_segment, dict):
                raw_segment = raw_segment.model_dump()

            segment: WhisperSegment = {
                "start": float(raw_segment.get("start", 0.0)),
                "end": float(raw_segment.get("end", 0.0)),
                "text": raw_segment.get("text") or "",
            }
            if raw_segment.get("speaker") is not None:
                segment["speaker"] = str(raw_segment["speaker"])
            segments.append(segment)

        # GPT transcription models return text-only JSON. The rest of the
        # application consumes segments, so expose the complete transcript as
        # one untimed segment without inventing timestamps.
        if text and not segments:
            segments.append(
                {
                    "start": 0.0,
                    "end": float(response_data.get("duration") or 0.0),
                    "text": text,
                }
            )
        elif not text and segments:
            text = "\n".join(segment["text"] for segment in segments)

        return {
            "text": text,
            "segments": segments,
            "language": response_data.get("language") or language,
        }

    def transcribe(
        self,
        audio: str,
        options: TranscribeOptions,
        language: str = "en",
    ) -> WhisperResult:
        prompt = os.getenv(
            "OPENAI_PROMPT", "This is a police radio dispatch transcript."
        )
        if options["initial_prompt"]:
            prompt += " The following words may appear: " + options["initial_prompt"]

        request: dict[str, Any] = {
            "model": self.model,
            "response_format": self.response_format,
            "language": language,
        }
        if self.is_diarization_model:
            request["chunking_strategy"] = "auto"
        else:
            request["prompt"] = prompt

        with open(audio, "rb") as audio_file:
            response = self.client.audio.transcriptions.create(
                file=audio_file,
                **request,
            )

        return self.normalize_response(response, language)

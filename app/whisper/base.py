from abc import ABC, abstractmethod
from typing import Any, NotRequired, Optional, TypedDict

from app.whisper.config import TranscriptCleanupConfig


class WhisperSegment(TypedDict):
    start: float
    end: float
    text: str
    speaker: NotRequired[str]


class WhisperResult(TypedDict):
    text: str
    segments: list[WhisperSegment]
    language: Optional[str]


def format_segment_text(segment: WhisperSegment) -> str:
    text = segment["text"].strip()
    speaker = segment.get("speaker")
    return f"Speaker {speaker}: {text}" if speaker and text else text


class TranscribeOptions(TypedDict):
    initial_prompt: str
    cleanup: bool
    vad_filter: bool
    decode_options: dict[str, Any]
    cleanup_config: TranscriptCleanupConfig


class BaseWhisper(ABC):
    @abstractmethod
    def transcribe(
        self,
        audio: str,
        options: TranscribeOptions,
        language: str = "en",
    ) -> WhisperResult:
        pass

from abc import ABC, abstractmethod
from typing import Any, List, Optional, TypedDict

from app.whisper.config import TranscriptCleanupConfig


class WhisperSegment(TypedDict):
    start: float
    end: float
    text: str


class WhisperResult(TypedDict):
    text: str
    segments: List[WhisperSegment]
    language: Optional[str]


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

from abc import ABC, abstractmethod
from typing import Any, List, Optional, TypedDict


class WhisperSegment(TypedDict):
    start: float
    end: float
    text: str


class WhisperResult(TypedDict):
    text: str
    segments: List[WhisperSegment]
    language: Optional[str]


class TranscriptKwargs(TypedDict):
    audio_file: str
    initial_prompt: str
    cleanup: bool
    vad_filter: bool


class BaseWhisper(ABC):
    @abstractmethod
    def transcribe(
        self,
        audio: str,
        language: str = "en",
        initial_prompt: str | None = None,
        vad_filter: bool = False,
        **decode_options: dict[Any, Any],
    ) -> WhisperResult:
        pass

    def transcribe_bulk(
        self,
        audio_files: list[str],
        lang_codes: list[str] = [],
        initial_prompts: list[str] = [],
        vad_filter: bool = False,
        **decode_options: dict[Any, Any],
    ) -> list[WhisperResult]:
        raise NotImplementedError

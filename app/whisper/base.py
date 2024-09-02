from abc import ABC, abstractmethod
from typing import List, Optional, TypedDict


class WhisperSegment(TypedDict):
    start: float
    end: float
    text: str


class WhisperResult(TypedDict):
    text: str
    segments: List[WhisperSegment]
    language: Optional[str]


class BaseWhisper(ABC):
    @abstractmethod
    def transcribe(
        self,
        audio: str,
        language: str = "en",
        initial_prompt: str | None = None,
        vad_filter: bool = False,
        **decode_options,
    ) -> WhisperResult:
        pass

    def transcribe_bulk(
        self,
        audio_files: list[str],
        lang_codes: list[str] = [],
        initial_prompts: list[str] = [],
        vad_filter: bool = False,
        **decode_options,
    ) -> list[WhisperResult]:
        raise NotImplementedError

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
    ) -> WhisperResult:
        pass

    def transcribe_bulk(
        self,
        audio_files: list[str],
        lang_codes: list[str] = [],
        initial_prompts: list[str] = [],
        vad_filter: bool = False,
    ) -> list[WhisperResult]:
        results = []
        for audio_file, lang_code, initial_prompt in zip(
            audio_files, lang_codes, initial_prompts
        ):
            results.append(
                self.transcribe(
                    audio_file,
                    language=lang_code,
                    initial_prompt=initial_prompt,
                    vad_filter=vad_filter,
                )
            )
        return results

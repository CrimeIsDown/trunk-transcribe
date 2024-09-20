import os

from app.models.metadata import Metadata, SrcListItem
from app.models.transcript import Transcript
from app.whisper.base import (
    TranscriptKwargs,
    WhisperSegment,
    WhisperResult,
)


def get_closest_src(srcList: list[SrcListItem], segment: WhisperSegment) -> SrcListItem:
    def closest_source(src: SrcListItem) -> float:
        return abs(src["pos"] - segment["start"])

    closest_src = min(srcList, key=closest_source)
    return closest_src


def build_transcribe_kwargs(
    metadata: Metadata, initial_prompt: str = ""
) -> TranscriptKwargs:
    initial_prompt = ""

    for src in metadata["srcList"]:
        if (
            len(src.get("transcript_prompt", ""))
            and src["transcript_prompt"] not in initial_prompt
        ):
            initial_prompt += " " + src["transcript_prompt"]

    return {
        "initial_prompt": initial_prompt,
        "cleanup": True,
        "vad_filter": os.getenv("VAD_FILTER_DIGITAL", "").lower() == "true",
    }


def process_response(response: WhisperResult, metadata: Metadata) -> Transcript:
    transcript = Transcript()

    for segment in response["segments"]:
        transcript.append(
            segment["text"].strip(),
            get_closest_src(metadata["srcList"], segment),
        )

    return transcript.validate()

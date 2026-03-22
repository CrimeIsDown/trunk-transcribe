import os

from app.models.metadata import Metadata, SrcListItem
from app.models.transcript import Transcript
from app.utils.cache import get_ttl_hash
from app.whisper.base import (
    TranscribeOptions,
    WhisperSegment,
    WhisperResult,
)
from app.whisper.config import get_transcript_cleanup_config, get_whisper_config


def get_closest_src(srcList: list[SrcListItem], segment: WhisperSegment) -> SrcListItem:
    def closest_source(src: SrcListItem) -> float:
        return abs(src["pos"] - segment["start"])

    closest_src = min(srcList, key=closest_source)
    return closest_src


def build_transcribe_options(
    metadata: Metadata, initial_prompt: str = ""
) -> TranscribeOptions:
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
        "decode_options": get_whisper_config(get_ttl_hash(cache_seconds=60)),
        "cleanup_config": get_transcript_cleanup_config(get_ttl_hash(cache_seconds=60)),
    }


def process_response(response: WhisperResult, metadata: Metadata) -> Transcript:
    transcript = Transcript()

    for segment in response["segments"]:
        transcript.append(
            segment["text"].strip(),
            get_closest_src(metadata["srcList"], segment),
        )

    return transcript.validate()

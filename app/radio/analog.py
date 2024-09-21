import os

from app.models.metadata import Metadata
from app.models.transcript import Transcript
from app.utils.cache import get_ttl_hash
from app.whisper.base import TranscribeOptions, WhisperResult
from app.whisper.config import get_transcript_cleanup_config, get_whisper_config


def build_transcribe_options(
    metadata: Metadata, initial_prompt: str = ""
) -> TranscribeOptions:
    return {
        "cleanup": True,
        "vad_filter": os.getenv("VAD_FILTER_ANALOG", "").lower() == "true",
        "initial_prompt": initial_prompt,
        "decode_options": get_whisper_config(get_ttl_hash(cache_seconds=60)),
        "cleanup_config": get_transcript_cleanup_config(get_ttl_hash(cache_seconds=60)),
    }


def process_response(response: WhisperResult, metadata: Metadata) -> Transcript:
    transcript = Transcript()

    for segment in response["segments"]:
        text = segment["text"].strip()
        if len(text):
            # TODO: use segment["start"] and segment["end"] as well
            transcript.append(text)

    return transcript.validate()

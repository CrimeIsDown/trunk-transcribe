import os

from app.models.metadata import Metadata
from app.models.transcript import Transcript
from app.whisper.base import TranscriptKwargs, WhisperResult


def build_transcribe_kwargs(
    metadata: Metadata, initial_prompt: str = ""
) -> TranscriptKwargs:
    return {
        "cleanup": True,
        "vad_filter": os.getenv("VAD_FILTER_ANALOG", "").lower() == "true",
        "initial_prompt": initial_prompt,
    }


def process_response(response: WhisperResult, metadata: Metadata) -> Transcript:
    transcript = Transcript()

    for segment in response["segments"]:
        text = segment["text"].strip()
        if len(text):
            # TODO: use segment["start"] and segment["end"] as well
            transcript.append(text)

    return transcript.validate()

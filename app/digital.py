import os
from threading import Lock

from .metadata import Metadata, SrcListItem
from .transcript import Transcript
from .whisper.base import WhisperSegment, WhisperResult
from .whisper.transcribe import transcribe


def get_closest_src(srcList: list[SrcListItem], segment: WhisperSegment):
    def closest_source(src):
        return abs(src["pos"] - segment["start"])

    closest_src = min(srcList, key=closest_source)
    return closest_src


def build_transcribe_kwargs(
    audio_file: str, metadata: Metadata, initial_prompt: str = ""
) -> dict:
    initial_prompt = ""

    for src in metadata["srcList"]:
        if (
            len(src.get("transcript_prompt", ""))
            and src["transcript_prompt"] not in initial_prompt
        ):
            initial_prompt += " " + src["transcript_prompt"]

    return {
        "audio_file": audio_file,
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


def transcribe_call(
    model, model_lock: Lock, audio_file: str, metadata: Metadata, prompt: str = ""
) -> Transcript:
    response = transcribe(
        model=model,
        model_lock=model_lock,
        **build_transcribe_kwargs(audio_file, metadata, prompt),
    )

    return process_response(response, metadata)

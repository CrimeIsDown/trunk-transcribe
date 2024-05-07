from threading import Lock

from .metadata import Metadata, SrcListItem
from .transcript import Transcript
from .whisper import WhisperResult, WhisperSegment, transcribe


def get_closest_src(srcList: list[SrcListItem], segment: WhisperSegment):
    def closest_source(src):
        return abs(src["pos"] - segment["start"])

    closest_src = min(srcList, key=closest_source)
    return closest_src


def build_transcribe_kwargs(audio_file: str, metadata: Metadata) -> dict:
    prev_transcript = ""

    for src in metadata["srcList"]:
        if (
            len(src.get("transcript_prompt", ""))
            and src["transcript_prompt"] not in prev_transcript
        ):
            prev_transcript += " " + src["transcript_prompt"]

    return {
        "audio_file": audio_file,
        "initial_prompt": prev_transcript,
        "cleanup": True,
        "vad_filter": False,
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
    model, model_lock: Lock, audio_file: str, metadata: Metadata
) -> Transcript:
    response = transcribe(
        model=model,
        model_lock=model_lock,
        **build_transcribe_kwargs(audio_file, metadata),
    )

    return process_response(response, metadata)

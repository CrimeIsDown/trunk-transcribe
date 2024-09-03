import os
from threading import Lock

from app.models.transcript import Transcript
from app.whisper.base import BaseWhisper, TranscriptKwargs, WhisperResult
from app.whisper.transcribe import transcribe


def build_transcribe_kwargs(
    audio_file: str, initial_prompt: str = ""
) -> TranscriptKwargs:
    return {
        "audio_file": audio_file,
        "cleanup": True,
        "vad_filter": os.getenv("VAD_FILTER_ANALOG", "").lower() == "true",
        "initial_prompt": initial_prompt,
    }


def process_response(response: WhisperResult) -> Transcript:
    transcript = Transcript()

    for segment in response["segments"]:
        text = segment["text"].strip()
        if len(text):
            # TODO: use segment["start"] and segment["end"] as well
            transcript.append(text)

    return transcript.validate()


def transcribe_call(
    model: BaseWhisper, model_lock: Lock, audio_file: str, prompt: str = ""
) -> Transcript:
    response = transcribe(
        model=model,
        model_lock=model_lock,
        **build_transcribe_kwargs(audio_file, prompt),
    )

    return process_response(response)
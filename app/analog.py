from threading import Lock

from .transcript import Transcript
from .whisper import transcribe


def transcribe_call(model, model_lock: Lock, audio_file: str) -> Transcript:
    response = transcribe(
        model=model,
        model_lock=model_lock,
        audio_file=audio_file,
        cleanup=True,
        vad_filter=True,
    )

    transcript = Transcript()

    for segment in response["segments"]:
        text = segment["text"].strip()
        if len(text):
            # TODO: use segment["start"] and segment["end"] as well
            transcript.append(text)

    return transcript.validate()

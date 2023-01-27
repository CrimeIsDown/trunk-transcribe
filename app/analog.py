import os
import subprocess
from glob import glob
from threading import Lock

from app.whisper import transcribe


def pad_silence(audio_file: str):
    basename = os.path.splitext(audio_file)[0]
    p = subprocess.run(
        [
            "sox",
            audio_file,
            f"{basename}-.wav",
            "silence",
            "1",
            "0.1",
            "0%",
            "1",
            "0.1",
            "0%",
            "pad",
            "0",
            "2",
            ":",
            "newfile",
            ":",
            "restart",
        ]
    )
    p.check_returncode()

    whisper_file = f"{basename}-whisper.wav"
    sox_args = sorted(glob(f"{basename}-*.wav"))
    sox_args.insert(0, "sox")
    sox_args.append(whisper_file)
    p = subprocess.run(sox_args)
    p.check_returncode()

    return whisper_file


def transcribe_call(model, model_lock: Lock, audio_file: str) -> str:
    prev_transcript = ""

    audio_file = pad_silence(audio_file)

    response = transcribe(
        model=model,
        model_lock=model_lock,
        audio_file=audio_file,
        initial_prompt=prev_transcript,
    )

    transcript = [segment["text"].strip() for segment in response["segments"]]
    if len(transcript) < 1:
        raise RuntimeError("Transcript empty/null")
    # Handle Whisper interpreting silence/non-speech
    if len(transcript) == 1 and (
        "Thank you." in transcript
        or "urn.com urn.schemas-microsoft-com.h" in transcript
    ):
        raise RuntimeError("No speech found")
    return "\n".join(transcript)

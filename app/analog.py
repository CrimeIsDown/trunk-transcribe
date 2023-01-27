import os
import subprocess
from glob import glob
from threading import Lock

from app.transcript import Transcript
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
    sox_args = sorted(glob(pathname=f"{basename}-*.wav"))
    sox_args.insert(0, "sox")
    sox_args.append(whisper_file)
    p = subprocess.run(sox_args)
    p.check_returncode()

    return whisper_file


def transcribe_call(model, model_lock: Lock, audio_file: str) -> Transcript:
    audio_file = pad_silence(audio_file)

    response = transcribe(
        model=model,
        model_lock=model_lock,
        audio_file=audio_file,
    )

    transcript = Transcript()

    for segment in response["segments"]:
        text = segment["text"].strip()
        if len(text):
            transcript.append(text)

    return transcript.validate()

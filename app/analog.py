import os
import subprocess
from glob import glob
from threading import Lock

from .transcript import Transcript
from .whisper import transcribe


def pad_silence(audio_file: str):  # pragma: no cover
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
    split_files = glob(pathname=f"{basename}-*.wav")
    sox_args = sorted(split_files)
    sox_args.insert(0, "sox")
    sox_args.append(whisper_file)
    p = subprocess.run(sox_args)

    try:
        p.check_returncode()
    except Exception as e:
        os.unlink(whisper_file)
        raise e
    finally:
        for filename in split_files:
            os.unlink(filename)

    return whisper_file


def transcribe_call(model, model_lock: Lock, audio_file: str) -> Transcript:
    audio_file = pad_silence(audio_file)

    response = transcribe(
        model=model, model_lock=model_lock, audio_file=audio_file, cleanup=True
    )

    transcript = Transcript()

    for segment in response["segments"]:
        text = segment["text"].strip()
        if len(text):
            # TODO: use segment["start"] and segment["end"] as well
            transcript.append(text)

    return transcript.validate()

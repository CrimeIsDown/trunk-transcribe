import os
import subprocess
from glob import glob
from app.whisper import transcribe


def transcribe_call(audio_file: str, metadata: dict) -> str:
    # We don't use metadata currently so remove it from memory
    del metadata
    prev_transcript = ""

    basename = os.path.splitext(audio_file)[0]
    whisper_file = f"{basename}-whisper.wav"

    split = True

    if split:
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
        sox_args = sorted(glob(f"{basename}-*.wav"))
        sox_args.insert(0, "sox")
        sox_args.append(whisper_file)
        p = subprocess.run(sox_args)
        p.check_returncode()
    else:
        whisper_file = audio_file

    response = transcribe(audio_file=whisper_file, initial_prompt=prev_transcript)

    transcript = [segment["text"].strip() for segment in response["segments"]]
    if len(transcript) < 1:
        raise RuntimeError("Transcript empty/null")
    # When the transcript is just "Thank you." it's almost never speech
    if len(transcript) == 1 and "Thank you." in transcript:
        raise RuntimeError("No speech found")
    return "\n".join(transcript)

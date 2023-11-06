import os
import subprocess
from threading import Lock

from .metadata import Metadata, SrcListItem
from .transcript import Transcript
from .whisper import transcribe


# TODO: write tests
def dedupe_srclist(srclist: list[SrcListItem]) -> list[SrcListItem]:
    prev_src = None
    new_srclist = []
    for src in srclist:
        if prev_src != src["src"]:
            new_srclist.append(src)
            prev_src = src["src"]
    return new_srclist


def extract_src_audio(
    audio_file: str, src: SrcListItem, nextSrc: SrcListItem | None
) -> str | None:  # pragma: no cover
    src_file = f"{os.path.splitext(audio_file)[0]}-{src['src']}.wav"
    start = src["pos"]
    trim_args = ["sox", audio_file, src_file, "trim", f"={start}"]
    if nextSrc:
        end = nextSrc["pos"]
        trim_args.append(f"={end}")

    trim_call = subprocess.run(trim_args)
    trim_call.check_returncode()

    length_call = subprocess.run(
        ["sox", "--i", "-D", src_file], text=True, stdout=subprocess.PIPE
    )
    length_call.check_returncode()
    if float(length_call.stdout) < 1:
        return None

    return src_file


# TODO: write tests
def transcribe_call(
    model, model_lock: Lock, audio_file: str, metadata: Metadata
) -> Transcript:
    transcript = Transcript()

    prev_transcript = ""
    srcList = dedupe_srclist(metadata["srcList"])
    for i in range(len(srcList)):
        src = srcList[i]
        try:
            nextSrc = srcList[i + 1]
        except IndexError:
            nextSrc = None
        src_file = extract_src_audio(audio_file, src, nextSrc)
        if not src_file:
            continue

        if len(src.get("transcript_prompt", "")):
            prev_transcript += " " + src["transcript_prompt"]

        response = transcribe(
            model=model,
            model_lock=model_lock,
            audio_file=src_file,
            initial_prompt=prev_transcript,
        )

        # TODO: use segments instead
        text = response["text"].strip() if response["text"] else ""

        transcript.append(text, src)

        prev_transcript = text

    return transcript.validate()

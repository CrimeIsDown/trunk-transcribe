import os
import subprocess
from threading import Lock

from whisper import Whisper

from app.metadata import Metadata, SrcListItem
from app.whisper import transcribe


def dedupe_srclist(srclist: list[SrcListItem]) -> list[SrcListItem]:
    prev_src = None
    new_srclist = []
    for src in srclist:
        if prev_src != src["src"]:
            new_srclist.append(src)
            prev_src = src["src"]
    return new_srclist


# TODO: Break this up into a smaller function
def transcribe_call(
    model: Whisper, model_lock: Lock, audio_file: str, metadata: Metadata
) -> str:
    result = []

    prev_transcript = ""
    srcList = dedupe_srclist(metadata["srcList"])
    for i in range(0, len(srcList)):
        src = srcList[i]
        src_id = str(src["src"])
        src_file = os.path.splitext(audio_file)[0] + "-" + src_id + ".wav"
        start = src["pos"]
        trim_args = ["sox", audio_file, src_file, "trim", f"={start}"]
        try:
            end = srcList[i + 1]["pos"]
            trim_args.append(f"={end}")
        except IndexError:
            pass

        trim_call = subprocess.run(trim_args)
        trim_call.check_returncode()

        length_call = subprocess.run(
            ["soxi", "-D", src_file], text=True, stdout=subprocess.PIPE
        )
        length_call.check_returncode()
        if float(length_call.stdout) < 1:
            continue

        if len(src.get("transcript_prompt", "")):
            prev_transcript += " " + src["transcript_prompt"]

        response = transcribe(
            model=model,
            model_lock=model_lock,
            audio_file=src_file,
            initial_prompt=prev_transcript,
        )

        transcript = response["text"].strip() if response["text"] else None
        # Handle Whisper interpreting silence/non-speech
        if not transcript or len(transcript) < 2 or transcript == "urn.com urn.schemas-microsoft-com.h":
            transcript = "(unintelligible)"

        src_tag = src["tag"] if len(src["tag"]) else src_id

        result.append((src_id, src_tag, transcript))

        prev_transcript = transcript

    if len(result) < 1:
        raise RuntimeError("Transcript empty/null")

    # If it is just unintelligible, don't bother
    if len(result) == 1 and result[0][1] == "(unintelligible)":
        raise RuntimeError("No speech found")

    return "\n".join(
        [
            f'<i data-src="{src_id}">{src_tag}:</i> {transcript}'
            for src_id, src_tag, transcript in result
        ]
    )

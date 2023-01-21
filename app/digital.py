import os
import subprocess
from app.whisper import transcribe


def dedupe_srclist(srclist: list[dict]) -> list[dict]:
    prev_src = None
    new_srclist = []
    for src in srclist:
        if prev_src != src["src"]:
            new_srclist.append(src)
            prev_src = src["src"]
    return new_srclist


def transcribe_call(audio_file: str, metadata: dict) -> str:
    result = []

    prev_transcript = ""
    srcList = dedupe_srclist(metadata["srcList"])
    for i in range(0, len(srcList)):
        src = srcList[i]
        src_file = os.path.splitext(audio_file)[0] + "-" + str(src["src"]) + ".wav"
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

        response = transcribe(src_file, prev_transcript)

        transcript = response["text"]
        if not transcript or len(transcript.strip()) < 2:
            transcript = "(unintelligible)"
        else:
            transcript = transcript.strip()

        speaker_name = src["tag"] if len(src["tag"]) else str(src["src"])

        result.append((speaker_name, transcript))

        prev_transcript = transcript

    if len(result) < 1:
        raise RuntimeError("Transcript empty/null")

    # If it is just unintelligible, don't bother
    if len(result) == 1 and result[0][1] == "(unintelligible)":
        raise RuntimeError("No speech found")

    return "\n".join([f"<i>{src}:</i> {transcript}" for src, transcript in result])

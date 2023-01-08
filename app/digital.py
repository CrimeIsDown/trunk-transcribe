import os
import subprocess
import re
from app.config import get_radio_id_replacements, get_ttl_hash
from app.whisper import transcribe


def parse_radio_id(input: str, system: str) -> tuple[str, str]:
    radio_id_replacements = get_radio_id_replacements(get_ttl_hash(cache_seconds=60))

    if system in radio_id_replacements.keys():
        replacements = radio_id_replacements[system]
        for replacement, patterns in replacements.items():
            for pattern in patterns:
                match = re.compile(pattern).match(input)
                if match:
                    groups = match.groups()
                    if len(groups):
                        replacement = replacement.format(
                            int(match.groups()[0]), int(match.groups()[0])
                        )
                    return tuple(replacement.split(","))

    return (input, "")


def transcribe_call(audio_file: str, metadata: dict) -> str:
    result = ""

    prev_transcript = ""
    for i in range(0, len(metadata["srcList"])):
        src = metadata["srcList"][i]["src"]

        src_file = os.path.splitext(audio_file)[0] + "-" + str(src) + ".wav"
        start = metadata["srcList"][i]["pos"]
        trim_args = ["sox", audio_file, src_file, "trim", f"={start}"]
        try:
            while src == metadata["srcList"][i + 1]["src"]:
                i += 1
            end = metadata["srcList"][i + 1]["pos"]
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

        try:
            prev_transcript += " " + metadata["talkgroup_description"].split("|")[1]
        except:
            pass
        parsed_src, parsed_src_prompt = parse_radio_id(str(src), metadata["short_name"])
        if len(parsed_src_prompt):
            prev_transcript += f" {parsed_src_prompt}"

        src = (
            metadata["srcList"][i]["tag"]
            if len(metadata["srcList"][i]["tag"])
            else parsed_src
        )

        response = transcribe(src_file, prev_transcript)

        transcript = response["text"]
        if not transcript or len(transcript.strip()) < 2:
            transcript = "(unintelligible)"
        else:
            transcript = transcript.strip()

        result += f"<i>{src}:</i> {transcript}\n"

        prev_transcript = transcript

    return result

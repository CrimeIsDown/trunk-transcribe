#!/usr/bin/env python3

import json
import logging
import os
import re
import subprocess
import tempfile
from base64 import b64decode
from glob import glob
from threading import Lock

import requests
import whisper
from celery import Celery

broker_url = os.getenv("CELERY_BROKER_URL")
result_backend = os.getenv("CELERY_RESULT_BACKEND")
celery = Celery("worker", broker=broker_url, backend=result_backend)

model = None
model_lock = Lock()


def load_model() -> whisper.Whisper:
    global model
    if not model:
        model_name = os.getenv("WHISPER_MODEL", "")
        model = whisper.load_model(model_name)
    return model


def parse_radio_id(
    input: str, system: str, radio_id_replacements: dict
) -> tuple[str, str]:
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


def whisper_transcribe(audio_file: str, initial_prompt: str = "") -> dict:
    with model_lock:
        return load_model().transcribe(
            audio_file, language="en", initial_prompt=initial_prompt
        )


def transcribe_digital(audio_file: str, metadata: dict) -> str:
    try:
        r = requests.get(
            url=f"{os.getenv('API_BASE_URL')}/config/radio-ids.json"
        )
        r.raise_for_status()
        radio_id_replacements = r.json()
    except:
        with open("config/radio-ids.json") as file:
            radio_id_replacements = json.loads(file.read())

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
        parsed_src, parsed_src_prompt = parse_radio_id(
            str(src), metadata["short_name"], radio_id_replacements
        )
        if len(parsed_src_prompt):
            prev_transcript += f" {parsed_src_prompt}"

        src = (
            metadata["srcList"][i]["tag"]
            if len(metadata["srcList"][i]["tag"])
            else parsed_src
        )

        response = whisper_transcribe(src_file, prev_transcript)

        transcript = response["text"]
        if not transcript or len(transcript.strip()) < 2:
            transcript = "(unintelligible)"
        else:
            transcript = transcript.strip()

        result += f"<i>{src}:</i> {transcript}\n"

        prev_transcript = transcript

    return result


def transcribe_analog(audio_file: str, metadata: dict) -> str:
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

    response = whisper_transcribe(
        audio_file=whisper_file, initial_prompt=prev_transcript
    )

    transcript = [segment["text"].strip() for segment in response["segments"]]
    if len(transcript) < 1:
        raise RuntimeError("Transcript empty/null")
    # When the transcript is just "Thank you." it's almost never speech
    if len(transcript) == 1 and "Thank you." in transcript:
        raise RuntimeError("No speech found")
    return "\n".join(transcript)


def convert_to_ogg(audio_file: str) -> str:
    ogg_file = tempfile.NamedTemporaryFile(delete=False, suffix=".ogg")
    ogg_file.close()
    p = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            audio_file,
            "-c:a",
            "libopus",
            "-b:a",
            "128k",
            ogg_file.name,
        ]
    )
    p.check_returncode()
    return ogg_file.name


def get_telegram_channel(
    metadata: dict, telegram_channel_mappings: dict
) -> dict | None:
    for regex, mapping in telegram_channel_mappings.items():
        if re.compile(regex).match(f"{metadata['talkgroup']}@{metadata['short_name']}"):
            return mapping

    return None


def post_transcription(
    voice_file: str,
    metadata: dict,
    transcript: str,
    debug: bool = False,
) -> dict:
    try:
        r = requests.get(
            url=f"{os.getenv('API_BASE_URL')}/config/telegram-channels.json"
        )
        r.raise_for_status()
        telegram_channel_mappings = r.json()
    except:
        with open("config/telegram-channels.json") as file:
            telegram_channel_mappings = json.loads(file.read())

    channel = (
        get_telegram_channel(metadata, telegram_channel_mappings)
        or telegram_channel_mappings["default"]
    )

    if channel["append_talkgroup"]:
        transcript = transcript + f"\n<b>{metadata['talkgroup_tag']}</b>"

    data = {
        "chat_id": channel["chat_id"],
        "parse_mode": "HTML",
        "caption": transcript,
    }

    if debug:
        return data

    response = requests.post(
        url=f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}/sendVoice",
        data=data,
        files={"voice": open(voice_file, "rb")},
        timeout=(5, 15),
    )

    logging.debug(response.json())
    return response.json()


def transcribe(metadata: dict, audio_file: str, debug: bool) -> dict:
    voice_file = None
    try:
        # Ensure we have a valid audio file and frontload conversion
        voice_file = convert_to_ogg(audio_file=audio_file)

        if metadata["audio_type"] == "digital":
            transcript = transcribe_digital(audio_file=audio_file, metadata=metadata)
        elif metadata["audio_type"] == "analog":
            transcript = transcribe_analog(audio_file=audio_file, metadata=metadata)
        else:
            raise Exception(f"Audio type {metadata['audio_type']} not supported")

        logging.debug(transcript)

        result = post_transcription(
            voice_file=voice_file, metadata=metadata, transcript=transcript, debug=debug
        )
    finally:
        if voice_file:
            os.unlink(voice_file)
        os.unlink(audio_file)
        basename = os.path.splitext(audio_file)[0]
        for file in glob(f"{basename}-*.wav"):
            os.unlink(file)

    return result


@celery.task(name="transcribe")
def transcribe_task(metadata: dict, audio_file_b64: str, debug: bool = False) -> dict:
    audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    audio_file.write(b64decode(audio_file_b64))
    audio_file.close()

    return transcribe(metadata=metadata, audio_file=audio_file.name, debug=debug)

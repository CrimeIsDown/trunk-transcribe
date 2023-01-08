import subprocess
import tempfile
from os.path import dirname


def convert_to_mp3(audio_file: str) -> str:
    dir = dirname(audio_file)
    mp3_file = tempfile.NamedTemporaryFile(delete=False, dir=dir, suffix=".mp3")
    mp3_file.close()
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
            "libmp3lame",
            "-b:a",
            "32k",
            mp3_file.name,
        ]
    )
    p.check_returncode()
    return mp3_file.name


def convert_to_ogg(audio_file: str) -> str:
    dir = dirname(audio_file)
    ogg_file = tempfile.NamedTemporaryFile(delete=False, dir=dir, suffix=".ogg")
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

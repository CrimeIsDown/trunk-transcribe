import subprocess
import tempfile
from datetime import datetime
from functools import lru_cache
from os.path import dirname

from cachetools import cached
from cachetools.keys import hashkey

from app.metadata import Metadata


def __convert_file(
    audio_file: str,
    format: str,
    ffmpeg_args: list[str],
    metadata: Metadata | None = None,
) -> str:
    metadata_args = []
    if metadata:
        start_time = datetime.fromtimestamp(metadata["start_time"])
        date = start_time.strftime("%Y-%m-%d")
        year = start_time.strftime("%Y")
        artist = ""
        if len(metadata["srcList"]):
            artist = ", ".join(
                set([src["tag"] for src in metadata["srcList"] if len(src["tag"])])
            )
        if not len(artist):
            artist = metadata["talkgroup_description"]
        metadata_args = [
            "-metadata",
            "composer=trunk-recorder",
            "-metadata",
            f"date={date}",
            "-metadata",
            f"year={year}",
            "-metadata",
            f'title={metadata["talkgroup_tag"]}',
            "-metadata",
            f"artist={artist}",
            "-metadata",
            f'album={metadata["talkgroup_group"]}',
        ]

    dir = dirname(audio_file)
    file = tempfile.NamedTemporaryFile(delete=False, dir=dir, suffix=f".{format}")
    file.close()
    p = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            audio_file,
        ]
        + ffmpeg_args
        + metadata_args
        + [file.name]
    )
    p.check_returncode()
    return file.name


@lru_cache()
def convert_to_wav(audio_file: str) -> str:
    return __convert_file(
        audio_file,
        "wav",
        [
            "-c:a",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
        ],
    )


@cached(cache={}, key=lambda audio_file, metadata: hashkey(audio_file))
def convert_to_mp3(audio_file: str, metadata: Metadata) -> str:
    return __convert_file(
        audio_file,
        "mp3",
        [
            "-c:a",
            "libmp3lame",
            "-b:a",
            "32k",
        ],
        metadata,
    )


@cached(cache={}, key=lambda audio_file, metadata: hashkey(audio_file))
def convert_to_ogg(audio_file: str, metadata: Metadata) -> str:
    return __convert_file(
        audio_file,
        "ogg",
        [
            "-c:a",
            "libopus",
            "-b:a",
            "128k",
        ],
        metadata,
    )

import subprocess
import tempfile
from datetime import datetime
from functools import lru_cache

import pytz
from cachetools import cached
from cachetools.keys import hashkey

from ..models.metadata import Metadata


def _build_metadata_args(metadata: Metadata) -> list[str]:
    start_time = datetime.fromtimestamp(metadata["start_time"], tz=pytz.UTC)
    creation_time = start_time.strftime("%Y-%m-%d %H:%M:%S")
    date = start_time.strftime("%Y-%m-%d")
    year = start_time.strftime("%Y")
    artist = ""
    if len(metadata["srcList"]):
        artist = ", ".join(
            list(
                dict.fromkeys(
                    [src["tag"] for src in metadata["srcList"] if len(src["tag"])]
                )
            )
        )
    if not len(artist):
        artist = metadata["talkgroup_description"]
    return [
        "-metadata",
        "composer=trunk-recorder",
        "-metadata",
        f"creation_time={creation_time}",
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


def _convert_file(
    audio_file: str,
    format: str,
    ffmpeg_args: list[str],
    metadata: Metadata | None = None,
) -> str:
    metadata_args = _build_metadata_args(metadata) if metadata else []

    file = tempfile.NamedTemporaryFile(delete=False, suffix=f".{format}")
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
def convert_to_wav(audio_file: str) -> str:  # pragma: no cover
    return _convert_file(
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
def convert_to_mp3(audio_file: str, metadata: Metadata) -> str:  # pragma: no cover
    return _convert_file(
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
def convert_to_ogg(audio_file: str, metadata: Metadata) -> str:  # pragma: no cover
    return _convert_file(
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

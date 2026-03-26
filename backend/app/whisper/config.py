import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, TypedDict

_CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


@lru_cache()
def get_whisper_config(ttl_hash=None) -> dict[str, Any]:
    del ttl_hash

    whisper_kwargs = {
        "compression_ratio_threshold": 1.8,  # Try to prevent repetitive segments https://github.com/openai/whisper/discussions/192
        "beam_size": 5,  # Standardize beam size for better performance
    }
    config = _CONFIG_DIR / "whisper.json"
    if os.path.isfile(config):
        with open(config) as file:
            whisper_kwargs = json.load(file)
    return whisper_kwargs


class TranscriptCleanupConfigItem(TypedDict):
    pattern: str
    replacement: str
    match_type: str
    action: str
    is_hallucination: bool


type TranscriptCleanupConfig = list[TranscriptCleanupConfigItem]


@lru_cache()
def get_transcript_cleanup_config(ttl_hash=None) -> TranscriptCleanupConfig:
    del ttl_hash

    config = _CONFIG_DIR / "transcript_cleanup.json"
    if os.path.isfile(config):
        with open(config) as file:
            return json.load(file)
    return []

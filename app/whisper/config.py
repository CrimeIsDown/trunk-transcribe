import json
import os
from functools import lru_cache


@lru_cache()
def get_whisper_config(ttl_hash=None) -> dict:  # type: ignore
    del ttl_hash

    whisper_kwargs = {
        "compression_ratio_threshold": 1.8,  # Try to prevent repetitive segments https://github.com/openai/whisper/discussions/192
        "beam_size": 5,  # Standardize beam size for better performance
    }
    config = "config/whisper.json"
    if os.path.isfile(config):
        with open(config) as file:
            whisper_kwargs = json.load(file)
    return whisper_kwargs


@lru_cache()
def get_transcript_cleanup_config(ttl_hash=None) -> list[dict]:  # type: ignore
    del ttl_hash

    config = "config/transcript_cleanup.json"
    if os.path.isfile(config):
        with open(config) as file:
            return json.load(file)  # type: ignore
    return []

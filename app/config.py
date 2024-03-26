import json
import os
from functools import lru_cache
from time import time
from typing_extensions import Optional, TypedDict

from . import api_client
from .geocoding import Geo


class LocationAlertConfig(TypedDict):
    geo: Geo
    radius: Optional[float]
    travel_time: Optional[int]


class AlertConfig(TypedDict):
    channels: list[str]
    keywords: Optional[list[str]]
    location: Optional[LocationAlertConfig]


class NotificationConfig(TypedDict):
    channels: list[str]
    append_talkgroup: bool
    alerts: list[AlertConfig]


@lru_cache()
def get_notifications_config(
    ttl_hash=None,
) -> dict[str, NotificationConfig]:  # pragma: no cover
    del ttl_hash

    path = "config/notifications.json"
    try:
        custom_config_url = os.getenv("NOTIFICATIONS_CONFIG_URL")
        if custom_config_url:
            return api_client.call("get", "", url=custom_config_url)
        else:
            return api_client.call("get", path)
    except Exception as e:
        # If we have a local copy of the config, fallback to that
        if os.path.isfile(path):
            with open(path) as file:
                return json.load(file)
        else:
            raise e


@lru_cache()
def get_whisper_config(ttl_hash=None) -> dict:  # pragma: no cover
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
def get_transcript_cleanup_config(ttl_hash=None) -> list[dict]:  # pragma: no cover
    del ttl_hash

    config = "config/transcript_cleanup.json"
    if os.path.isfile(config):
        with open(config) as file:
            return json.load(file)
    return []


def get_ttl_hash(cache_seconds=3600):  # pragma: no cover
    """Return the same value within `cache_seconds` time period"""
    return round(time() / cache_seconds)

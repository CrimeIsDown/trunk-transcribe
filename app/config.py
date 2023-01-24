import json
import os
from functools import lru_cache
from time import time
from typing import TypedDict

import requests


class AlertConfig(TypedDict):
    channels: list[str]
    keywords: list[str]


class NotificationConfig(TypedDict):
    channels: list[str]
    append_talkgroup: bool
    alerts: list[AlertConfig]


@lru_cache()
def get_notifications_config(ttl_hash=None) -> dict[str, NotificationConfig]:
    del ttl_hash

    path = "config/notifications.json"
    api_key = os.getenv("API_KEY")
    if api_key:
        headers = {"Authorization": f"Bearer {api_key}"}
    else:
        headers = None
    try:
        r = requests.get(
            url=f"{os.getenv('API_BASE_URL')}/{path}",
            timeout=5,
            headers=headers,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        # If we have a local copy of the config, fallback to that
        if os.path.isfile(path):
            with open(path) as file:
                return json.load(file)
        else:
            raise e


@lru_cache()
def get_whisper_config(ttl_hash=None) -> dict:
    del ttl_hash

    whisper_kwargs = {}
    config = "config/whisper.json"
    if os.path.isfile(config):
        with open(config) as file:
            whisper_kwargs = json.load(file)
    return whisper_kwargs


def get_ttl_hash(cache_seconds=3600):
    """Return the same value within `cache_seconds` time period"""
    return round(time() / cache_seconds)

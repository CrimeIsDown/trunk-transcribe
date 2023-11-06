import json
import os
from functools import lru_cache
from time import time
from typing import TypedDict

from . import api_client


class AlertConfig(TypedDict):
    channels: list[str]
    keywords: list[str]


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

    whisper_kwargs = {}
    config = "config/whisper.json"
    if os.path.isfile(config):
        with open(config) as file:
            whisper_kwargs = json.load(file)
    return whisper_kwargs


def get_ttl_hash(cache_seconds=3600):  # pragma: no cover
    """Return the same value within `cache_seconds` time period"""
    return round(time() / cache_seconds)

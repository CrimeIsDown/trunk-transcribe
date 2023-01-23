from functools import lru_cache
import logging
import os
import json
from time import time
from typing import TypedDict
import requests

class ChannelConfig(TypedDict):
    chat_id: str
    append_talkgroup: bool
    alerts: dict[str, list[str]]


@lru_cache()
def get_notifications_config(ttl_hash=None) -> dict[str, ChannelConfig]:
    del ttl_hash
    path = "config/notifications.json"
    api_key = os.getenv('API_KEY')
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


def get_ttl_hash(cache_seconds=3600):
    """Return the same value within `cache_seconds` time period"""
    return round(time() / cache_seconds)

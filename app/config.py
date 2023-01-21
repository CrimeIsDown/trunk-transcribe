from functools import lru_cache
import os
import json
from time import time
from typing import TypedDict
import requests

api_key = os.getenv("API_KEY", "")


class ChannelConfig(TypedDict):
    chat_id: str
    append_talkgroup: bool
    alerts: dict[str, list[str]]


@lru_cache()
def get_channels_config(ttl_hash=None) -> dict[str, ChannelConfig]:
    del ttl_hash
    try:
        r = requests.get(
            url=f"{os.getenv('API_BASE_URL')}/config/channels.json",
            timeout=5,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        r.raise_for_status()
        return r.json()
    except:
        with open("config/channels.json") as file:
            return json.load(file)


def get_ttl_hash(cache_seconds=3600):
    """Return the same value within `cache_seconds` time period"""
    return round(time() / cache_seconds)

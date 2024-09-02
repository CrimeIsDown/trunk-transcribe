import json
import os
from functools import lru_cache
from typing import Optional, TypedDict

from ..utils import api_client
from ..geocoding.geocoding import Geo


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

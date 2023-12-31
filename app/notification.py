import logging
import os
import re
from datetime import datetime
from sys import platform
from time import time
from typing import Tuple

import pytz
from apprise import Apprise, AppriseAttachment, NotifyFormat
from geopy import distance, point

from .config import (
    AlertConfig,
    NotificationConfig,
    get_notifications_config,
    get_ttl_hash,
)
from .geocoding import GeoResponse, calculate_route_duration
from .metadata import Metadata
from .transcript import Transcript


# TODO: write tests
def truncate_transcript(transcript: str) -> str:
    # Telegram has a 1024 char max for the caption, so truncate long ones
    # (we use less than 1024 to account for long URLs and what we will add next)
    transcript_max_len = 1024 - 200
    if len(transcript) > transcript_max_len:
        transcript = f"{transcript[:transcript_max_len]}... (truncated)"
    return transcript


def add_channels(apprise: Apprise, channels: list) -> Apprise:  # pragma: no cover
    for channel in channels:
        if channel.startswith("tgram://"):
            channel = channel.replace(
                "$TELEGRAM_BOT_TOKEN",
                os.getenv("TELEGRAM_BOT_TOKEN", "no-token-defined"),
            )

        logging.debug("Adding channel: " + channel)
        apprise.add(channel)
    return apprise


# TODO: write tests
def build_suffix(
    metadata: Metadata, add_talkgroup: bool = False, search_url: str = ""
) -> str:
    suffix = []
    if add_talkgroup:
        suffix.append(f"<b>{metadata['talkgroup_tag']}</b>")

    # If delayed by over DELAYED_CALL_THRESHOLD add delay warning
    if time() - metadata["stop_time"] > float(os.getenv("DELAYED_CALL_THRESHOLD", 120)):
        linux_format = "%-m/%-d/%Y %-I:%M:%S %p %Z"
        windows_format = linux_format.replace("-", "#")
        timestamp = (
            datetime.fromtimestamp(metadata["start_time"], tz=pytz.UTC)
            .astimezone(pytz.timezone(os.getenv("DISPLAY_TZ", "America/Chicago")))
            .strftime(windows_format if platform == "win32" else linux_format)
        )
        suffix.append(f"<br /><i>{timestamp} (delayed)</i>")

    if len(search_url):
        suffix.append(f'<br /><a href="{search_url}">View in search</a>')

    return "<br />".join(suffix)


# TODO: write tests
def check_transcript_for_alert_keywords(
    transcript: str, keywords: list[str]
) -> tuple[list[str], list[str]]:
    matched_keywords = []
    matched_lines = []
    for line in transcript.splitlines():
        matches = [
            keyword
            for keyword in keywords
            if re.compile(rf"\b{keyword}\b", re.IGNORECASE).search(line)
        ]
        if len(matches):
            matched_keywords += matches
            matched_lines.append(line)
    return list(set(matched_keywords)), matched_lines


# TODO: write tests
def get_matching_config(
    metadata: Metadata, config: dict[str, NotificationConfig]
) -> list[NotificationConfig]:
    return [
        c
        for regex, c in config.items()
        if re.compile(regex).search(f"{metadata['talkgroup']}@{metadata['short_name']}")
    ]


def send_notifications(
    raw_audio_url: str,
    metadata: Metadata,
    transcript: Transcript,
    geo: GeoResponse | None,
    search_url: str,
):  # pragma: no cover
    # If delayed over our MAX_CALL_AGE, don't bother sending to Telegram
    max_age = float(os.getenv("MAX_CALL_AGE", 1200))
    if max_age > 0 and time() - metadata["stop_time"] > max_age:
        logging.debug("Not sending notifications since call is too old")
        return

    config = get_notifications_config(get_ttl_hash(cache_seconds=60))

    transcript_html = transcript.html

    for match in get_matching_config(metadata, config):
        if len(match["channels"]):
            notify(match, metadata, transcript_html, raw_audio_url)
        for alert_config in match["alerts"]:
            if len(alert_config["channels"]):
                should_send, title, body = should_send_alert(
                    alert_config, transcript_html, geo
                )
                if should_send:
                    notify(
                        alert_config, metadata, body, raw_audio_url, title, search_url
                    )


def notify(
    config: NotificationConfig | AlertConfig,
    metadata: Metadata,
    body: str,
    audio_file: str,
    title: str = "",
    search_url: str = "",
):  # pragma: no cover
    # Captions are only 1024 chars max so we must truncate the transcript to fit for Telegram
    if "tgram://" in str(config["channels"]):
        body = truncate_transcript(body)

    should_add_talkgroup = (
        config["append_talkgroup"] if "append_talkgroup" in config else True
    )
    suffix = build_suffix(metadata, should_add_talkgroup, search_url)

    add_channels(Apprise(), config["channels"]).notify(
        body="<br />".join([body, suffix]),
        body_format=NotifyFormat.HTML,
        title=title,
        attach=AppriseAttachment(audio_file),
    )


def should_send_alert(
    config: AlertConfig, transcript: str, geo: GeoResponse | None
) -> Tuple[bool, str, str]:
    """
    Notification options:
    - keyword
    - location / radius
    - location / travel time
    - LLM based (TBA)
    """

    condition_results = []
    title = ""
    body = transcript

    keywords = config.get("keywords")
    if keywords:
        matched_keywords, matched_lines = check_transcript_for_alert_keywords(
            transcript, keywords
        )

        match = len(matched_keywords) > 0
        condition_results.append(match)
        if match:
            title = (
                title + " " + ", ".join(matched_keywords) + " detected in transcript"
            )

            # Avoid duplicating the transcript if we don't have to
            transcript_excerpt = "<br />".join(matched_lines)
            if transcript_excerpt != transcript:
                body = transcript_excerpt + "<br />&#8213;&#8213;&#8213;<br />" + body

    location = config.get("location")
    if location and geo:
        incident_location = point.Point(geo["geo"]["lat"], geo["geo"]["lng"])
        user_location = point.Point(location["geo"]["lat"], location["geo"]["lng"])

        if max_radius := location.get("radius"):
            distance_to_incident = distance.distance(
                user_location, incident_location
            ).miles
            match = distance_to_incident < float(max_radius)
            condition_results.append(match)
            if match:
                title = (
                    title
                    + f" Location {geo['geo_formatted_address']} ({distance_to_incident:.2f} miles away) detected in transcript"
                )

        if travel_time_max := location.get("travel_time"):
            duration = calculate_route_duration(user_location, incident_location)
            match = duration < int(travel_time_max)
            condition_results.append(match)
            if match:
                duration_min = duration / 60
                title = (
                    title
                    + f" Location {geo['geo_formatted_address']} ({duration_min:.0f} minutes away) detected in transcript"
                )

    # if config.get("custom_gpt_prompt"):
    # TODO: send the prompt and transcript to the LLM to determine if we should notify

    behavior = "AND"
    should_send = (
        False not in condition_results
        if behavior == "AND"
        else True in condition_results
    )

    return should_send, title.strip(), body.strip()

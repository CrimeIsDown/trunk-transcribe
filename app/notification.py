import logging
import os
import re
from datetime import datetime
from sys import platform
from time import time

import pytz
from apprise import Apprise, AppriseAttachment, NotifyFormat

from .config import (
    AlertConfig,
    NotificationConfig,
    get_notifications_config,
    get_ttl_hash,
)
from .conversion import convert_to_ogg
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
    search_url: str,
):  # pragma: no cover
    # If delayed over our MAX_CALL_AGE, don't bother sending to Telegram
    max_age = float(os.getenv("MAX_CALL_AGE", 1200))
    if max_age > 0 and time() - metadata["stop_time"] > max_age:
        logging.debug("Not sending notifications since call is too old")
        return

    config = get_notifications_config(get_ttl_hash(cache_seconds=60))

    transcript_html = transcript.html
    # We cannot delete this ogg file immediately as Apprise sends notifications in the background
    ogg_file = convert_to_ogg(raw_audio_url, metadata)

    for match in get_matching_config(metadata, config):
        notify_channels(match, ogg_file, metadata, transcript_html)
        for alert_config in match["alerts"]:
            send_alert(alert_config, metadata, transcript_html, ogg_file, search_url)


def notify_channels(
    config: NotificationConfig,
    audio_file: str,
    metadata: Metadata,
    transcript: str,
):  # pragma: no cover
    # Validate we actually have somewhere to send the notification
    if not len(config["channels"]):
        return

    # Captions are only 1024 chars max so we must truncate the transcript to fit for Telegram
    if "tgram://" in str(config["channels"]):
        transcript = truncate_transcript(transcript)

    suffix = build_suffix(metadata, config["append_talkgroup"])

    add_channels(Apprise(), config["channels"]).notify(
        body="<br />".join([transcript, suffix]),
        body_format=NotifyFormat.HTML,
        attach=AppriseAttachment(audio_file),
    )


def send_alert(
    config: AlertConfig,
    metadata: Metadata,
    transcript: str,
    audio_file: str,
    search_url: str,
):  # pragma: no cover
    # Validate we actually have somewhere to send the notification
    if not len(config["channels"]):
        return

    # Captions are only 1024 chars max so we must truncate the transcript to fit for Telegram
    if "tgram://" in str(config["channels"]):
        transcript = truncate_transcript(transcript)

    # If we haven't already appended the talkgroup, do it for the alert
    suffix = build_suffix(metadata, add_talkgroup=True, search_url=search_url)

    matched_keywords, matched_lines = check_transcript_for_alert_keywords(
        transcript, config["keywords"]
    )

    if len(matched_keywords):
        title = ", ".join(matched_keywords) + " detected in transcript"

        # Avoid duplicating the transcript if we don't have to
        transcript_excerpt = "<br />".join(matched_lines)
        if transcript_excerpt == transcript:
            body = transcript
        else:
            body = transcript_excerpt + "<br />&#8213;&#8213;&#8213;<br />" + transcript

        add_channels(Apprise(), config["channels"]).notify(
            body="<br />".join([body, suffix]),
            body_format=NotifyFormat.HTML,
            title=title,
            attach=AppriseAttachment(audio_file),
        )

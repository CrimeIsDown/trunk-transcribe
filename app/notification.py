import logging
import os
import re
from datetime import datetime, timezone
from sys import platform
from time import time

import pytz
from apprise import Apprise
from apprise.plugins.NotifyTelegram import NotifyTelegram as NotifyTelegramBase

from app.config import (
    AlertConfig,
    NotificationConfig,
    get_notifications_config,
    get_ttl_hash,
)
from app.conversion import convert_to_ogg
from app.metadata import Metadata
from app.notification_plugins.NotifyTelegram import NotifyTelegram
from app.transcript import Transcript


def truncate_transcript(transcript: str) -> str:
    # Telegram has a 1024 char max for the caption, so truncate long ones
    # (we use less than 1024 to account for HTML and what we will add next)
    transcript_max_len = 950
    if len(transcript) > transcript_max_len:
        transcript = f"{transcript[:transcript_max_len]}... (truncated)"
    return transcript


def build_suffix(metadata: Metadata, add_talkgroup: bool = False) -> str:
    suffix = []
    if add_talkgroup:
        suffix.append(f"<b>{metadata['talkgroup_tag']}</b>")

    # If delayed by over DELAYED_CALL_THRESHOLD add delay warning
    if time() - metadata["stop_time"] > float(os.getenv("DELAYED_CALL_THRESHOLD", 120)):
        linux_format = "%-m/%-d/%Y %-I:%M:%S %p %Z"
        windows_format = linux_format.replace("-", "#")
        timestamp = (
            datetime.fromtimestamp(metadata["start_time"], tz=timezone.utc)
            .astimezone(pytz.timezone(os.getenv("TZ", "America/Chicago")))
            .strftime(windows_format if platform == "win32" else linux_format)
        )
        suffix.append(f"\n<i>{timestamp} (delayed)</i>")

    return "\n".join(suffix)


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
    return matched_keywords, matched_lines


def send_notifications(
    audio_file: str, metadata: Metadata, transcript: Transcript, raw_audio_url: str
):
    # If delayed over our MAX_CALL_AGE, don't bother sending to Telegram
    max_age = float(os.getenv("MAX_CALL_AGE", 1200))
    if max_age > 0 and time() - metadata["stop_time"] > max_age:
        logging.debug("Not sending notifications since call is too old")
        return

    config = get_notifications_config(get_ttl_hash(cache_seconds=60))

    matches = [
        c
        for regex, c in config.items()
        if re.compile(regex).search(f"{metadata['talkgroup']}@{metadata['short_name']}")
    ]

    transcript_html = transcript.html.replace("<br>", "\n")

    for match in matches:
        notify_channels(match, audio_file, metadata, transcript_html)
        for alert_config in match["alerts"]:
            send_alert(
                alert_config,
                metadata,
                transcript_html,
                raw_audio_url,
            )


def notify_channels(
    config: NotificationConfig,
    audio_file: str,
    metadata: Metadata,
    transcript: str,
):
    # Validate we actually have somewhere to send the notification
    if not len(config["channels"]):
        return

    voice_file = convert_to_ogg(audio_file=audio_file)

    suffix = build_suffix(metadata, config["append_talkgroup"])

    # Monkey patch NotifyTelegram so we can send voice messages with captions
    NotifyTelegramBase.send = NotifyTelegram.send  # type: ignore
    NotifyTelegramBase.send_media = NotifyTelegram.send_media  # type: ignore

    notifier = Apprise()

    for channel in config["channels"]:
        if channel.startswith("tgram://"):
            # Captions are only 1024 chars max so we must truncate the transcript to fit
            transcript = truncate_transcript(transcript)
        notifier.add(
            # TODO: Figure out how to allow other envs to be used in a safe way
            channel.replace(
                "$TELEGRAM_BOT_TOKEN",
                os.getenv("TELEGRAM_BOT_TOKEN", "no-token-defined"),
            )
        )

    notifier.notify(body="\n".join([transcript, suffix]), attach=voice_file)  # type: ignore


def send_alert(
    config: AlertConfig,
    metadata: Metadata,
    transcript: str,
    raw_audio_url: str,
):
    # Validate we actually have somewhere to send the notification
    if not len(config["channels"]):
        return

    # If we haven't already appended the talkgroup, do it for the alert
    suffix = build_suffix(metadata, add_talkgroup=True)

    matched_keywords, matched_lines = check_transcript_for_alert_keywords(
        transcript, config["keywords"]
    )

    if len(matched_keywords):
        notifier = Apprise()

        for channel in config["channels"]:
            notifier.add(
                channel.replace(
                    "$TELEGRAM_BOT_TOKEN",
                    os.getenv("TELEGRAM_BOT_TOKEN", "no-token-defined"),
                )
            )

        body = "<u>" + ", ".join(matched_keywords) + " detected in transcript</u>\n"

        # Avoid duplicating the transcript if we don't have to
        transcript_excerpt = "\n".join(matched_lines)
        if transcript_excerpt == transcript:
            body += transcript
        else:
            body += transcript_excerpt + "\n---\n" + transcript

        body += f'\n{suffix}\n<a href="{raw_audio_url}">Listen to transmission</a>'

        notifier.notify(body=body)

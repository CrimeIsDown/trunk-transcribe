import logging
import os
import re
from datetime import datetime, timezone
from sys import platform
from time import time

import pytz
from apprise import Apprise
from apprise.plugins.NotifyTelegram import NotifyTelegram as NotifyTelegramBase

from app.config import ChannelConfig, get_notifications_config, get_ttl_hash
from app.conversion import convert_to_ogg
from app.metadata import Metadata
from app.notification_plugins.NotifyTelegram import NotifyTelegram


def get_config(metadata: Metadata) -> ChannelConfig | None:
    channels = get_notifications_config(get_ttl_hash(cache_seconds=60))
    for regex, config in channels.items():
        if re.compile(regex).match(f"{metadata['talkgroup']}@{metadata['short_name']}"):
            return config

    return None


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

    # If delayed by over 2 mins add delay warning
    if time() - metadata["stop_time"] > 120:
        linux_format = "%-m/%-d/%Y %-I:%M:%S %p %Z"
        windows_format = linux_format.replace("-", "#")
        timestamp = (
            datetime.fromtimestamp(metadata["start_time"], tz=timezone.utc)
            .astimezone(pytz.timezone(os.getenv("TZ", "America/Chicago")))
            .strftime(windows_format if platform == "win32" else linux_format)
        )
        suffix.append(f"\n<i>{timestamp} (delayed)</i>")

    return "\n".join(suffix)


def send_notifications(
    audio_file: str, metadata: Metadata, transcript: str, raw_audio_url: str
):
    # If delayed over our MAX_CALL_AGE, don't bother sending to Telegram
    max_age = float(os.getenv("MAX_CALL_AGE", 1200))
    if max_age > 0 and time() - metadata["stop_time"] > max_age:
        logging.debug("Not sending notifications since call is too old")
        return

    channel = get_config(metadata)

    # If we don't have a config for this channel, we don't want to send any notifications for it
    if not channel:
        return

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return

    voice_file = convert_to_ogg(audio_file=audio_file)

    transcript = truncate_transcript(transcript)
    suffix = build_suffix(metadata, channel["append_talkgroup"])

    # Monkey patch NotifyTelegram so we can send voice messages with captions
    NotifyTelegramBase.send = NotifyTelegram.send  # type: ignore
    NotifyTelegramBase.send_media = NotifyTelegram.send_media  # type: ignore

    notifier = Apprise()

    notifier.add(f"tgram://{bot_token}/{channel['chat_id']}")

    notifier.notify(body="\n".join([transcript, suffix]), attach=voice_file)  # type: ignore

    for alert_chat_id, alert_keywords in channel["alerts"].items():
        send_alert(
            alert_chat_id,
            alert_keywords,
            metadata,
            transcript,
            channel,
            raw_audio_url,
            bot_token,
        )


def send_alert(
    alert_chat_id: str,
    alert_keywords: list[str],
    metadata: Metadata,
    transcript: str,
    channel: ChannelConfig,
    raw_audio_url: str,
    bot_token: str,
):
    # If we haven't already appended the talkgroup, do it for the alert
    suffix = build_suffix(metadata, add_talkgroup=True)

    matched_keywords = []
    matched_lines = []
    for line in transcript.splitlines():
        matches = [
            keyword for keyword in alert_keywords if keyword.lower() in line.lower()
        ]
        if len(matches):
            matched_keywords += matches
            matched_lines.append(line)

    if len(matched_keywords):
        notifier = Apprise()
        notifier.add(f"tgram://{bot_token}/{alert_chat_id}")

        body = "<u>" + ", ".join(matched_keywords) + " detected in transcript</u>\n"

        # Avoid duplicating the transcript if we don't have to
        transcript_excerpt = "\n".join(matched_lines)
        if transcript_excerpt == transcript:
            body += transcript
        else:
            body += transcript_excerpt + "\n---\n" + transcript

        body += f'\n{suffix}\n<a href="{raw_audio_url}">Listen to transmission</a>'

        notifier.notify(body=body)

import logging
import os
import re
from datetime import datetime, timezone
from sys import platform
from time import time

import pytz
from telegram import Bot, Chat, Message

from app.config import ChannelConfig, get_channels_config, get_ttl_hash
from app.conversion import convert_to_ogg
from app.metadata import Metadata


def get_channel_config(metadata: Metadata) -> ChannelConfig | None:
    channels = get_channels_config(get_ttl_hash(cache_seconds=60))
    for regex, config in channels.items():
        if re.compile(regex).match(f"{metadata['talkgroup']}@{metadata['short_name']}"):
            return config

    return None


def prep_transcript(metadata: Metadata, transcript: str, channel: ChannelConfig):
    # Telegram has a 1024 char max for the caption, so truncate long ones
    # (we use less than 1024 to account for HTML and what we will add next)
    transcript_max_len = 950
    if len(transcript) > transcript_max_len:
        transcript = f"{transcript[:transcript_max_len]}... (truncated)"

    if channel["append_talkgroup"]:
        transcript = transcript + f"\n<b>{metadata['talkgroup_tag']}</b>"

    # If delayed by over 2 mins add delay warning
    if time() - metadata["stop_time"] > 120:
        linux_format = "%-m/%-d/%Y %-I:%M:%S %p %Z"
        windows_format = linux_format.replace("-", "#")
        timestamp = (
            datetime.fromtimestamp(metadata["start_time"], tz=timezone.utc)
            .astimezone(pytz.timezone(os.getenv("TZ", "America/Chicago")))
            .strftime(windows_format if platform == "win32" else linux_format)
        )
        transcript = transcript + f"\n\n<i>{timestamp} (delayed)</i>"

    return transcript


def build_alert(alert_chat_id: str, alert_keywords: list[str], message: Message):
    matched_keywords = [
        keyword
        for keyword in alert_keywords
        if keyword.lower() in message.caption.lower()
    ]
    if len(matched_keywords):
        logging.debug(
            f"Found keywords {str(matched_keywords)} in message {message.message_id}, forwarding to {alert_chat_id}"
        )
        return {
            "chat_id": int(alert_chat_id),
            "from_chat_id": message.chat.id,
            "message_id": message.message_id,
        }


async def send_message(
    audio_file: str,
    metadata: Metadata,
    transcript: str,
    dry_run: bool = False,
):
    # If delayed over 20 minutes, don't bother sending to Telegram
    if time() - metadata["stop_time"] > 1200:
        return

    channel = get_channel_config(metadata)

    # If we don't have a config for this channel, we don't want to upload it to Telegram
    if not channel:
        return

    voice_file = convert_to_ogg(audio_file=audio_file)

    transcript = prep_transcript(metadata, transcript, channel)

    async with Bot(os.getenv("TELEGRAM_BOT_TOKEN", "")) as bot:
        with open(voice_file, "rb") as file:
            voice = file.read()
        kwargs = {
            "chat_id": int(channel["chat_id"]),
            "voice": voice,
            "caption": transcript,
            "parse_mode": "HTML",
        }
        if dry_run:
            kwargs.pop("voice")
            logging.debug(f"Would have sent voice message {str(kwargs)}")
            message = Message(
                message_id=-1,
                chat=Chat(id=int(channel["chat_id"]), type=Chat.CHANNEL),
                date=datetime.now(),
                caption=transcript,
            )
        else:
            message = await bot.send_voice(**kwargs)
            logging.debug(message)

        for alert_chat_id, alert_keywords in channel["alerts"].items():
            alert = build_alert(alert_chat_id, alert_keywords, message)
            if alert:
                if dry_run:
                    logging.debug(f"Would have forwarded message {str(alert)}")
                else:
                    forwarded_message = await bot.forward_message(**alert)
                    logging.debug(forwarded_message)

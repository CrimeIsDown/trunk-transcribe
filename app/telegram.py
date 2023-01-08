import os
import re
import logging
from datetime import datetime
from app.config import get_telegram_channel_mappings, get_ttl_hash
from telegram import Bot, Chat, Message

from app.conversion import convert_to_ogg


def get_telegram_channel(metadata: dict) -> dict:
    telegram_channel_mappings = get_telegram_channel_mappings(
        get_ttl_hash(cache_seconds=60)
    )
    for regex, mapping in telegram_channel_mappings.items():
        if re.compile(regex).match(f"{metadata['talkgroup']}@{metadata['short_name']}"):
            return mapping

    raise RuntimeError("Transcribing not setup for talkgroup")


async def send_message(
    audio_file: str,
    metadata: dict,
    transcript: str,
    dry_run: bool = False,
):
    channel = get_telegram_channel(metadata)

    voice_file = convert_to_ogg(audio_file=audio_file)

    if channel["append_talkgroup"]:
        transcript = transcript + f"\n<b>{metadata['talkgroup_tag']}</b>"

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
            matched_keywords = [
                keyword
                for keyword in alert_keywords
                if keyword.lower() in message.caption.lower()
            ]
            if len(matched_keywords):
                logging.debug(
                    f"Found keywords {str(matched_keywords)} in message {message.message_id}, forwarding to {alert_chat_id}"
                )
                kwargs = {
                    "chat_id": int(alert_chat_id),
                    "from_chat_id": message.chat.id,
                    "message_id": message.message_id,
                }
                if dry_run:
                    logging.debug(f"Would have forwarded message {str(kwargs)}")
                else:
                    forwarded_message = await bot.forward_message(**kwargs)
                    logging.debug(forwarded_message)

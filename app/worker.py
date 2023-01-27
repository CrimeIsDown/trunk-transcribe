#!/usr/bin/env python3

import logging
import os
import tempfile
from base64 import b64decode

# This is needed so all workers are synced to the same timezone
os.environ["TZ"] = "UTC"

import requests
from celery import Celery
from celery.exceptions import Reject
from dotenv import load_dotenv

from app.analog import transcribe_call as transcribe_analog
from app.conversion import convert_to_wav
from app.digital import transcribe_call as transcribe_digital
from app.metadata import Metadata
from app.notification import send_notifications
from app.search import index_call
from app.storage import upload_raw_audio

load_dotenv()

broker_url = os.getenv("CELERY_BROKER_URL")
result_backend = os.getenv("CELERY_RESULT_BACKEND")
celery = Celery(
    "worker",
    broker=broker_url,
    backend=result_backend,
    task_routes={
        "retranscribe": {"queue": "retranscribe"},
        "transcribe": {"queue": "transcribe"},
    },
    task_cls="app.whisper:WhisperTask",
)


def transcribe(
    model,
    model_lock,
    metadata: Metadata,
    audio_file: str,
    id: str | None = None,
    raw_audio_url: str | None = None,
    index_name: str | None = None,
) -> str:
    try:
        if metadata["audio_type"] == "digital":
            transcript = transcribe_digital(model, model_lock, audio_file, metadata)
        elif metadata["audio_type"] == "analog":
            transcript = transcribe_analog(model, model_lock, audio_file)
        else:
            raise Reject(f"Audio type {metadata['audio_type']} not supported")
    except RuntimeError as e:
        return str(e)
    logging.debug(transcript)

    if not raw_audio_url:
        raw_audio_url = upload_raw_audio(metadata, audio_file)
    index_call(metadata, raw_audio_url, transcript, id, index_name=index_name)

    # Do not send Telegram messages for calls we already have transcribed previously
    if not id:
        send_notifications(audio_file, metadata, transcript, raw_audio_url)

    return transcript


@celery.task(name="transcribe")
def transcribe_task(metadata: Metadata, audio_file_b64: str) -> str:
    with tempfile.TemporaryDirectory() as tempdir:
        audio_file = tempfile.NamedTemporaryFile(delete=False, dir=tempdir)
        audio_file.write(b64decode(audio_file_b64))
        audio_file.close()
        wav_file = convert_to_wav(audio_file.name)

        return transcribe(
            transcribe_task.model,
            transcribe_task.model_lock,
            metadata,
            audio_file=wav_file,
        )


@celery.task(name="retranscribe")
def retranscribe_task(
    metadata: Metadata, audio_url: str, id: str, index_name: str | None = None
) -> str:
    with tempfile.TemporaryDirectory() as tempdir:
        with requests.get(audio_url, stream=True) as r:
            r.raise_for_status()
            mp3_file = tempfile.NamedTemporaryFile(
                delete=False, dir=tempdir, suffix=".mp3"
            )
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                mp3_file.write(chunk)
            mp3_file.close()

        audio_file = convert_to_wav(mp3_file.name)

        return transcribe(
            retranscribe_task.model,
            retranscribe_task.model_lock,
            metadata,
            audio_file,
            id,
            raw_audio_url=audio_url,
            index_name=index_name,
        )

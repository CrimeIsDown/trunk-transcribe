#!/usr/bin/env python3

from hashlib import sha256
import json
import logging
import os
import signal
import tempfile
from typing import Tuple

import requests
import sentry_sdk
from celery import Celery, signals, states
from celery.exceptions import Reject
from datauri import DataURI
from dotenv import load_dotenv
from sentry_sdk.integrations.celery import CeleryIntegration


load_dotenv()

from . import api_client
from .analog import transcribe_call as transcribe_analog
from .conversion import convert_to_wav
from .digital import transcribe_call as transcribe_digital
from .geocoding import GeoResponse, lookup_geo
from .metadata import Metadata
from .notification import send_notifications
from .search import index_call
from .transcript import Transcript

sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[
            CeleryIntegration(),
        ],
        release=os.getenv("GIT_COMMIT"),
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=float(os.getenv("SENTRY_TRACE_SAMPLE_RATE", "0.1")),
        _experiments={
            "profiles_sample_rate": float(
                os.getenv("SENTRY_PROFILE_SAMPLE_RATE", "0.1")
            ),
        },
    )

broker_url = os.getenv("CELERY_BROKER_URL")
result_backend = os.getenv("CELERY_RESULT_BACKEND")
celery = Celery(
    "worker",
    broker=broker_url,
    backend=result_backend,
    task_cls="app.whisper:WhisperTask",
    task_acks_late=True,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    worker_prefetch_multiplier=1,
    timezone="UTC",
)

task_counts = {}


@signals.task_prerun.connect
def task_prerun(**kwargs):
    # If we've only had failing tasks on this worker, terminate it
    if states.SUCCESS not in task_counts and len(
        [
            count
            for state, count in task_counts.items()
            if state in states.EXCEPTION_STATES and count > 5
        ]
    ):
        logging.fatal("Exceeded job failure threshold, exiting...\n" + str(task_counts))
        os.kill(
            os.getppid(),
            signal.SIGQUIT if hasattr(signal, "SIGQUIT") else signal.SIGTERM,
        )


@signals.task_postrun.connect
def task_postrun(**kwargs):
    if kwargs["state"] not in task_counts:
        task_counts[kwargs["state"]] = 0
    task_counts[kwargs["state"]] += 1


@signals.task_unknown.connect
def task_unknown(**kwargs):
    logging.exception(kwargs["exc"])
    logging.fatal("Unknown job, exiting...")
    os.kill(os.getpid(), signal.SIGQUIT)


def transcribe(
    model,
    model_lock,
    metadata: Metadata,
    audio_file: str,
) -> Tuple[Transcript | None, GeoResponse | None]:
    try:
        if (
            metadata["audio_type"] == "digital"
            or metadata["audio_type"] == "digital tdma"
        ):
            transcript = transcribe_digital(model, model_lock, audio_file, metadata)
        elif metadata["audio_type"] == "analog":
            transcript = transcribe_analog(model, model_lock, audio_file)
        else:
            raise Reject(f"Audio type {metadata['audio_type']} not supported")
    except RuntimeError as e:
        logging.warn(e)
        return None, None
    logging.debug(transcript.json)

    geo = lookup_geo(metadata, transcript)

    return transcript, geo


def transcribe_and_index(
    model,
    model_lock,
    metadata: Metadata,
    audio_file: str,
    raw_audio_url: str,
    id: str | None = None,
    index_name: str | None = None,
) -> str:
    try:
        if (
            metadata["audio_type"] == "digital"
            or metadata["audio_type"] == "digital tdma"
        ):
            transcript = transcribe_digital(model, model_lock, audio_file, metadata)
        elif metadata["audio_type"] == "analog":
            transcript = transcribe_analog(model, model_lock, audio_file)
        else:
            raise Reject(f"Audio type {metadata['audio_type']} not supported")
    except RuntimeError as e:
        return repr(e)
    logging.debug(transcript.json)

    geo = lookup_geo(metadata, transcript)

    new_call = False
    if not id:
        raw_metadata = json.dumps(metadata)
        id = sha256(raw_metadata.encode("utf-8")).hexdigest()
        new_call = True

    search_url = index_call(id, metadata, raw_audio_url, transcript, geo, index_name)

    # Do not send Telegram messages for calls we already have transcribed previously
    if new_call:
        send_notifications(raw_audio_url, metadata, transcript, geo, search_url)

    return transcript.txt


@celery.task(name="transcribe")
def transcribe_task(
    metadata: Metadata,
    audio_url: str,
    id: str | None = None,
    index_name: str | None = None,
    whisper_implementation: str | None = None,
) -> str:
    mp3_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    if audio_url.startswith("data:"):
        uri = DataURI(audio_url)
        mp3_file.write(uri.data)  # type: ignore
        mp3_file.close()
    else:
        with requests.get(audio_url, stream=True) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                mp3_file.write(chunk)
            mp3_file.close()

    audio_file = convert_to_wav(mp3_file.name)

    os.unlink(mp3_file.name)

    try:
        result = transcribe_and_index(
            transcribe_task.model(whisper_implementation),
            transcribe_task.model_lock,
            metadata,
            audio_file,
            audio_url,
            id,
            index_name,
        )
    finally:
        os.unlink(audio_file)

    return result


@celery.task(name="transcribe_db")
def transcribe_from_db_task(
    id: int, whisper_implementation: str | None = None
) -> str | None:
    call = api_client.call("get", f"calls/{id}")
    metadata = call["raw_metadata"]
    audio_url = call["raw_audio_url"]

    mp3_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    if audio_url.startswith("data:"):
        uri = DataURI(audio_url)
        mp3_file.write(uri.data)  # type: ignore
        mp3_file.close()
    else:
        with requests.get(audio_url, stream=True) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                mp3_file.write(chunk)
            mp3_file.close()

    try:
        audio_file = convert_to_wav(mp3_file.name)
    finally:
        os.unlink(mp3_file.name)

    try:
        transcript, geo = transcribe(
            transcribe_task.model(whisper_implementation),
            transcribe_task.model_lock,
            metadata,
            audio_file,
        )
    finally:
        os.unlink(audio_file)

    if transcript:
        call = api_client.call(
            "patch",
            f"calls/{id}",
            json={"raw_transcript": transcript.transcript, "geo": geo},
        )

        return transcript.txt

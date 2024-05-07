#!/usr/bin/env python3

from hashlib import sha256
import json
import logging
import os
import signal
import tempfile

import requests
import sentry_sdk
from celery import Celery, signals, states
from celery.exceptions import Reject
from datauri import DataURI
from dotenv import load_dotenv
from sentry_sdk.integrations.celery import CeleryIntegration


load_dotenv()

from . import api_client, analog, digital, whisper
from .conversion import convert_to_wav
from .exceptions import WhisperException
from .geocoding import lookup_geo
from .metadata import Metadata
from .notification import send_notifications
from .search import index_call, make_next_index
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
) -> Transcript | None:
    try:
        if "digital" in metadata["audio_type"]:
            transcript = digital.transcribe_call(
                model, model_lock, audio_file, metadata
            )
        elif metadata["audio_type"] == "analog":
            transcript = analog.transcribe_call(model, model_lock, audio_file)
        else:
            raise Reject(f"Audio type {metadata['audio_type']} not supported")
    except WhisperException as e:
        logging.warn(e)
        return None
    logging.debug(transcript.json)

    return transcript


def fetch_audio(audio_url: str) -> str:
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

    return audio_file


def transcribe_and_index(
    model,
    model_lock,
    metadata: Metadata,
    audio_file: str,
    raw_audio_url: str,
    id: str | None = None,
    index_name: str | None = None,
) -> str:
    transcript = transcribe(model, model_lock, metadata, audio_file)
    if not transcript:
        return ""

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
    audio_file = fetch_audio(audio_url)

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
        try:
            os.unlink(audio_file)
        except OSError:
            pass

    make_next_index()

    return result


@celery.task(name="transcribe_db")
def transcribe_from_db_task(
    id: int, whisper_implementation: str | None = None
) -> str | None:
    call = api_client.call("get", f"calls/{id}")
    metadata = call["raw_metadata"]
    audio_url = call["raw_audio_url"]

    audio_file = fetch_audio(audio_url)

    try:
        transcript = transcribe(
            transcribe_from_db_task.model(whisper_implementation),
            transcribe_from_db_task.model_lock,
            metadata,
            audio_file,
        )
    finally:
        try:
            os.unlink(audio_file)
        except OSError:
            pass

    if transcript:
        api_client.call(
            "patch",
            f"calls/{id}",
            json={"raw_transcript": transcript.transcript},
        )

        return transcript.txt


@celery.task(
    name="transcribe_db_batch",
    base=whisper.WhisperBatchTask,
    flush_every=50,
    flush_interval=10,
)
def transcribe_from_db_batch_task(requests):
    calls: list[tuple[int, Metadata, dict]] = []
    # TODO: consider splitting to one function for analog and another for digital
    vad_filter = True

    for request in requests:
        call = api_client.call("get", f"calls/{request.kwargs['id']}")
        metadata = call["raw_metadata"]
        audio_url = call["raw_audio_url"]

        audio_file = fetch_audio(audio_url)

        if "digital" in metadata["audio_type"]:
            calls.append(
                (
                    request.kwargs["id"],
                    metadata,
                    digital.build_transcribe_kwargs(audio_file, metadata),
                )
            )
            vad_filter = False
        elif metadata["audio_type"] == "analog":
            calls.append(
                (
                    request.kwargs["id"],
                    metadata,
                    analog.build_transcribe_kwargs(audio_file),
                )
            )
        else:
            raise Reject(f"Audio type {metadata['audio_type']} not supported")

    results = whisper.transcribe_bulk(
        transcribe_from_db_batch_task.model(),
        transcribe_from_db_batch_task.model_lock,
        audio_files=[kwargs["audio_file"] for _, _, kwargs in calls],
        initial_prompts=[kwargs.get("initial_prompt", "") for _, _, kwargs in calls],
        cleanup=calls[0][2]["cleanup"],
        vad_filter=vad_filter,
    )

    for (id, metadata, _), result in zip(calls, results):
        if not result:
            continue

        try:
            if "digital" in metadata["audio_type"]:
                transcript = digital.process_response(result, metadata)
            elif metadata["audio_type"] == "analog":
                transcript = analog.process_response(result)

            api_client.call(
                "patch",
                f"calls/{id}",
                json={"raw_transcript": transcript.transcript},
            )
        except Exception as e:
            logging.error(e)
            if not isinstance(e, WhisperException):
                sentry_sdk.capture_exception(e)
            continue

    return [result["text"] for result in results if result]

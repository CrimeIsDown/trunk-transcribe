#!/usr/bin/env python3

from hashlib import sha256
from multiprocessing.pool import AsyncResult
from typing import Optional
import json
import logging
import os
import signal

from celery import Celery, signals, states
from celery.exceptions import Reject
from dotenv import load_dotenv
from sentry_sdk.integrations.celery import CeleryIntegration
import sentry_sdk

load_dotenv()

from app.utils.storage import fetch_audio
from app.whisper.base import TranscribeOptions, WhisperResult
from app.whisper.transcribe import transcribe
from app.geocoding.geocoding import lookup_geo
from app.models.metadata import Metadata
from app.notifications.notification import send_notifications
from app.utils import api_client
from app.utils.exceptions import before_send
from app.search import search
from app.whisper.exceptions import WhisperException
from app.whisper.task import API_IMPLEMENTATIONS, WhisperTask

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
        before_send=before_send,
    )

CELERY_DEFAULT_QUEUE = os.getenv("CELERY_DEFAULT_QUEUE", "transcribe")
CELERY_GPU_QUEUE = f"{CELERY_DEFAULT_QUEUE}_gpu"

broker_url = os.getenv("CELERY_BROKER_URL")
result_backend = os.getenv("CELERY_RESULT_BACKEND")
celery = Celery(
    "worker",
    broker=broker_url,
    backend=result_backend,
    task_acks_late=True,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    worker_prefetch_multiplier=os.getenv("CELERY_PREFETCH_MULTIPLIER", 1),
    timezone="UTC",
)
celery.conf.task_default_queue = CELERY_DEFAULT_QUEUE

recent_job_results: list[str] = []

logger = logging.getLogger(__name__)


def queue_task(
    audio_url: str,
    metadata: Metadata,
    options: TranscribeOptions,
    whisper_implementation: Optional[str] = None,
    id: Optional[int | str] = None,
    index_name: Optional[str] = None,
) -> AsyncResult[str]:
    return (
        transcribe_task.s(options, audio_url, whisper_implementation).set(
            queue=CELERY_DEFAULT_QUEUE
            if os.getenv("WHISPER_IMPLEMENTATION") in API_IMPLEMENTATIONS
            else CELERY_GPU_QUEUE
        )
        | post_transcribe_task.s(metadata, audio_url, id, index_name).set(
            queue=f"post_{CELERY_DEFAULT_QUEUE}"
        )
    ).apply_async()


@signals.task_prerun.connect
def task_prerun(**kwargs):  # type: ignore
    # If we've only had failing tasks on this worker, terminate it
    if len(recent_job_results) == 5 and states.SUCCESS not in recent_job_results:
        logger.fatal(
            "Exceeded job failure threshold, exiting...\n" + str(recent_job_results)
        )
        os.kill(
            os.getppid(),
            signal.SIGQUIT if hasattr(signal, "SIGQUIT") else signal.SIGTERM,
        )


@signals.task_postrun.connect
def task_postrun(**kwargs):  # type: ignore
    recent_job_results.insert(0, kwargs["state"])
    if len(recent_job_results) > 5:
        recent_job_results.pop()


@signals.task_unknown.connect  # type: ignore
def task_unknown(**kwargs):  # type: ignore
    logger.exception(kwargs["exc"])
    logger.fatal("Unknown job, exiting...")
    os.kill(os.getpid(), signal.SIGQUIT)


@signals.task_retry.connect  # type: ignore
def task_retry(**kwargs):  # type: ignore
    if isinstance(kwargs["reason"], WhisperException):
        return
    logger.exception(kwargs["reason"])
    sentry_sdk.capture_exception(kwargs["reason"])
    if "CUDA error:" in str(kwargs["reason"]) or "CUDA out of memory" in str(
        kwargs["reason"]
    ):
        # Exit the worker process to avoid further errors by triggering Docker to automatically restart the worker
        os.kill(
            os.getppid(),
            signal.SIGQUIT if hasattr(signal, "SIGQUIT") else signal.SIGTERM,
        )
    logger.warning(f"Task {kwargs['request'].kwargsrepr} failed, retrying...")


@celery.task(base=WhisperTask, bind=True, name="transcribe_audio")
def transcribe_task(
    self,
    options: TranscribeOptions,
    audio_url: str,
    whisper_implementation: Optional[str] = None,
) -> WhisperResult:
    audio_file = fetch_audio(audio_url)
    try:
        return transcribe(
            model=self.model(whisper_implementation),  # type: ignore
            audio_file=audio_file,
            options=options,
        )
    finally:
        try:
            os.unlink(audio_file)
        except OSError:
            pass


@celery.task(name="post_transcribe")
def post_transcribe_task(
    result: WhisperResult,
    metadata: Metadata,
    raw_audio_url: str,
    id: Optional[int | str] = None,
    index_name: Optional[str] = None,
):
    logger.debug(result)

    if "digital" in metadata["audio_type"]:
        from app.radio.digital import process_response
    elif metadata["audio_type"] == "analog":
        from app.radio.analog import process_response
    else:
        raise Reject(
            f"Audio type {metadata['audio_type']} not supported", requeue=False
        )
    try:
        transcript = process_response(result, metadata)
    except WhisperException as e:
        logger.warning(e)
        return None

    geo = lookup_geo(metadata, transcript)

    if not id:
        raw_metadata = json.dumps(metadata)
        id = sha256(raw_metadata.encode("utf-8")).hexdigest()
    else:
        api_client.call(
            "patch",
            f"calls/{id}",
            json={"raw_transcript": transcript.transcript},
        )

    search_url = search.index_call(
        id, metadata, raw_audio_url, transcript, geo, index_name
    )

    send_notifications(raw_audio_url, metadata, transcript, geo, search_url)

    search.make_next_index()

    return transcript.txt

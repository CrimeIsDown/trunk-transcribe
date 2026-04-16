#!/usr/bin/env python3

from __future__ import annotations

import json
import logging
import os
import signal
from hashlib import sha256
from typing import TYPE_CHECKING, Optional

import requests
import sentry_sdk
from celery import Celery, signals, states
from celery.exceptions import Reject
from sentry_sdk.integrations.celery import CeleryIntegration

from app.core.config import (
    POST_TRANSCRIBE_QUEUE,
    settings,
)
from app.core.transcription_profiles import resolve_transcription_profile
from app.utils import api_client
from app.utils.exceptions import before_send
from app.utils.storage import fetch_audio
from app.whisper.base import TranscribeOptions, TranscribeTaskResult, WhisperResult
from app.whisper.exceptions import WhisperException
from app.whisper.task import TranscriptionTask
from app.whisper.transcribe import transcribe

if TYPE_CHECKING:
    # Keep these imports type-only so a transcribe-only worker can boot without
    # loading the DB/search stack during module import.
    from app.models.metadata import Metadata
    from app.search.adapters import SearchAdapter

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        auto_enabling_integrations=False,
        integrations=[
            CeleryIntegration(),
        ],
        release=settings.GIT_COMMIT,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=settings.SENTRY_TRACE_SAMPLE_RATE,
        _experiments={
            "profiles_sample_rate": settings.SENTRY_PROFILE_SAMPLE_RATE,
        },
        before_send=before_send,
    )

CELERY_DEFAULT_QUEUE = settings.CELERY_DEFAULT_QUEUE

celery = Celery(
    "worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    task_acks_late=True,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    worker_prefetch_multiplier=settings.CELERY_PREFETCH_MULTIPLIER,
)
celery.conf.task_default_queue = CELERY_DEFAULT_QUEUE
search_adapters: list[SearchAdapter] = []

recent_job_results: list[str] = []

logger = logging.getLogger(__name__)


def get_transcription_queue(
    transcription_profile: str | None = None,
) -> str:
    resolved_profile = resolve_transcription_profile(
        explicit_profile=transcription_profile,
        default_profile=settings.DEFAULT_TRANSCRIPTION_PROFILE,
    )
    return resolved_profile.queue_name


def queue_task(
    audio_url: str,
    metadata: Metadata,
    options: TranscribeOptions,
    transcription_profile: Optional[str] = None,
    id: Optional[int | str] = None,
    index_name: Optional[str] = None,
):
    transcription_queue = get_transcription_queue(transcription_profile)
    return (
        transcribe_task.s(options, audio_url, transcription_profile).set(
            queue=transcription_queue
        )
        | post_transcribe_task.s(metadata, audio_url, id, index_name).set(
            queue=POST_TRANSCRIBE_QUEUE
        )
    ).apply_async()


@signals.task_prerun.connect
def task_prerun(**kwargs):
    # If we've only had failing tasks on this worker, terminate it
    if len(recent_job_results) == 5 and states.SUCCESS not in recent_job_results:
        logger.fatal(
            "Exceeded job failure threshold, exiting...\n" + str(recent_job_results)
        )
        # If this is a vast.ai instance, delete itself since it must not be working properly
        vast_api_key = settings.CONTAINER_API_KEY
        vast_instance_id = settings.CONTAINER_ID
        if vast_api_key and vast_instance_id:
            logger.info("Deleting this vast.ai instance...")
            requests.delete(
                f"https://console.vast.ai/api/v0/instances/{vast_instance_id}/",
                headers={"Authorization": f"Bearer {vast_api_key}"},
                json={},
                timeout=5,
            )
        os.kill(
            os.getppid(),
            signal.SIGQUIT if hasattr(signal, "SIGQUIT") else signal.SIGTERM,
        )


@signals.task_postrun.connect
def task_postrun(**kwargs):
    recent_job_results.insert(0, kwargs["state"])
    if len(recent_job_results) > 5:
        recent_job_results.pop()


@signals.task_unknown.connect
def task_unknown(**kwargs):
    logger.exception(kwargs["exc"])
    logger.fatal("Unknown job, exiting...")
    os.kill(os.getpid(), signal.SIGQUIT)


@signals.task_retry.connect
def task_retry(**kwargs):
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


@celery.task(base=TranscriptionTask, bind=True, name="transcribe_audio")
def transcribe_task(
    self,
    options: TranscribeOptions,
    audio_url: str,
    transcription_profile: Optional[str] = None,
) -> TranscribeTaskResult:
    audio_file = fetch_audio(audio_url)
    transcription_provider, transcription_model = self.resolve_provider_and_model(
        transcription_profile
    )
    try:
        result = transcribe(
            model=self.model(transcription_profile),
            audio_file=audio_file,
            options=options,
        )
        return {
            "result": result,
            "transcription_provider": transcription_provider,
            "transcription_model": transcription_model,
        }
    finally:
        try:
            os.unlink(audio_file)
        except OSError:
            pass


@celery.task(name="post_transcribe")
def post_transcribe_task(
    result: TranscribeTaskResult | WhisperResult,
    metadata: Metadata,
    raw_audio_url: str,
    id: Optional[int | str] = None,
    index_name: Optional[str] = None,
):
    # post_transcribe is the only path that needs DB/search/geocoding modules.
    # Import them lazily so worker-only hosts can start with just queue/API env.
    from app.geocoding.geocoding import lookup_geo
    from app.notifications.notification import send_notifications
    from app.search.adapters import MeilisearchAdapter, TypesenseAdapter

    logger.debug(result)

    transcription_result = result
    enriched_metadata: Metadata = dict(metadata)
    if "result" in result:
        transcription_result = result["result"]
        enriched_metadata["transcription_provider"] = result["transcription_provider"]
        enriched_metadata["transcription_model"] = result["transcription_model"]

    if "digital" in enriched_metadata["audio_type"]:
        from app.radio.digital import process_response
    elif enriched_metadata["audio_type"] == "analog":
        from app.radio.analog import process_response
    else:
        raise Reject(
            f"Audio type {enriched_metadata['audio_type']} not supported", requeue=False
        )
    try:
        transcript = process_response(transcription_result, enriched_metadata)
    except WhisperException as e:
        logger.warning(e)
        return None

    geo = lookup_geo(enriched_metadata, transcript)

    if not id:
        raw_metadata = json.dumps(metadata)
        id = sha256(raw_metadata.encode("utf-8")).hexdigest()
    else:
        api_client.call(
            "patch",
            f"calls/{id}",
            json={
                "raw_metadata": enriched_metadata,
                "raw_transcript": transcript.transcript,
                "geo": geo,
            },
        )

    global search_adapters
    if not search_adapters:
        if settings.has_meilisearch:
            search_adapters.append(MeilisearchAdapter())
        if settings.has_typesense:
            search_adapters.append(TypesenseAdapter())

    for search in search_adapters:
        search_url = search.index_call(
            id, enriched_metadata, raw_audio_url, transcript, geo, index_name
        )

    try:
        send_notifications(raw_audio_url, enriched_metadata, transcript, geo, search_url)
    except Exception as e:
        logger.exception("Failed to send notifications", exc_info=e)

    return transcript.txt

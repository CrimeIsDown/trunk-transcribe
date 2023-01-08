#!/usr/bin/env python3

import asyncio
import logging
import os
import tempfile
from base64 import b64decode

from celery import Celery
from dotenv import load_dotenv

from app.search import index
from app.telegram import send_message

load_dotenv()

broker_url = os.getenv("CELERY_BROKER_URL")
result_backend = os.getenv("CELERY_RESULT_BACKEND")
celery = Celery("worker", broker=broker_url, backend=result_backend)


def transcribe(metadata: dict, audio_file: str, debug: bool) -> str:
    if metadata["audio_type"] == "digital":
        from app.digital import transcribe_call
    elif metadata["audio_type"] == "analog":
        from app.analog import transcribe_call
    else:
        raise Exception(f"Audio type {metadata['audio_type']} not supported")

    try:
        transcript = transcribe_call(audio_file=audio_file, metadata=metadata)
    except RuntimeError as e:
        return str(e)
    logging.debug(transcript)

    try:
        asyncio.run(
            send_message(
                audio_file=audio_file,
                metadata=metadata,
                transcript=transcript,
                dry_run=debug,
            )
        )
    except Exception as e:
        logging.error(e)
        pass

    index(metadata=metadata, audio_file=audio_file, transcript=transcript)

    return transcript


@celery.task(name="transcribe")
def transcribe_task(metadata: dict, audio_file_b64: str, debug: bool = False) -> str:
    with tempfile.TemporaryDirectory() as tempdir:
        audio_file = tempfile.NamedTemporaryFile(
            delete=False, dir=tempdir, suffix=".wav"
        )
        audio_file.write(b64decode(audio_file_b64))
        audio_file.close()

        return transcribe(metadata=metadata, audio_file=audio_file.name, debug=debug)

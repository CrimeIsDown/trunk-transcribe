#!/usr/bin/env python3

import json
import os
import tempfile

from celery.result import AsyncResult
from fastapi import (
    APIRouter,
    HTTPException,
    UploadFile,
)
from fastapi.responses import JSONResponse

from app.utils import storage
from app import worker


router = APIRouter()


@router.post("/tasks")
def queue_for_transcription(
    call_audio: UploadFile,
    call_json: UploadFile,
    whisper_implementation: str | None = None,
) -> JSONResponse:
    metadata = json.loads(call_json.file.read())

    if metadata["call_length"] < float(os.getenv("MIN_CALL_LENGTH", "2")):
        raise HTTPException(status_code=400, detail="Call too short to transcribe")

    if "digital" in metadata["audio_type"]:
        from app.radio.digital import build_transcribe_options
    elif metadata["audio_type"] == "analog":
        from app.radio.analog import build_transcribe_options
    else:
        raise HTTPException(
            status_code=400, detail=f"Audio type {metadata['audio_type']} not supported"
        )

    raw_audio = tempfile.NamedTemporaryFile(
        delete=False, suffix=f"_{call_audio.filename}"
    )
    while True:
        data = call_audio.file.read(1024 * 1024)
        if not data:
            raw_audio.close()
            break
        raw_audio.write(data)

    try:
        audio_url = storage.upload_raw_audio(metadata, raw_audio.name)
    finally:
        os.unlink(raw_audio.name)

    task = worker.queue_task(
        audio_url, metadata, build_transcribe_options(metadata), whisper_implementation
    )

    return JSONResponse({"task_id": task.id}, status_code=201)


@router.get("/tasks/{task_id}")
def get_status(task_id: str) -> JSONResponse:
    task_result: AsyncResult = AsyncResult(task_id, app=worker.celery)
    result = {
        "task_id": task_id,
        "task_status": task_result.status,
        "task_result": (
            repr(task_result.result)
            if isinstance(task_result.result, Exception)
            else task_result.result
        ),
    }
    return JSONResponse(result)

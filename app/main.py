#!/usr/bin/env python3

import json
from base64 import b64encode
import os

from celery.result import AsyncResult
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from .worker import get_telegram_channel, transcribe

app = FastAPI()


with open("config/telegram-channels.json") as file:
    telegram_channel_mappings = json.loads(file.read())


@app.post("/tasks")
def queue_for_transcription(
    call_audio: UploadFile,
    call_json: UploadFile,
    debug: bool | None = False,
):
    metadata = json.loads(call_json.file.read())

    if not get_telegram_channel(metadata):
        raise HTTPException(
            status_code=400, detail="Transcribing not setup for talkgroup"
        )

    if metadata["call_length"] < float(os.getenv("MIN_CALL_LENGTH", "2")):
        raise HTTPException(
            status_code=400, detail="Call $filename too short to transcribe"
        )

    audio_file_b64 = b64encode(call_audio.file.read()).decode("utf-8")
    task = transcribe.delay(
        metadata=metadata, audio_file_b64=audio_file_b64, debug=debug
    )
    return JSONResponse({"task_id": task.id}, status_code=201)


@app.get("/tasks/{task_id}")
def get_status(task_id):
    task_result = AsyncResult(task_id)
    result = {
        "task_id": task_id,
        "task_status": task_result.status,
        "task_result": task_result.result,
    }
    return JSONResponse(result)

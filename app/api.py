#!/usr/bin/env python3

import json
import os
from base64 import b64encode
import tempfile

from celery.result import AsyncResult
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, Request
from fastapi.responses import JSONResponse
from app.storage import upload_raw_audio

from app.worker import transcribe_task, celery as celery_app

load_dotenv()

app = FastAPI()


@app.middleware("http")
async def authenticate(request: Request, call_next):
    api_key = os.getenv("API_KEY", "")

    if api_key and request.headers.get("Authorization", "") != f"Bearer {api_key}":
        return JSONResponse(content={"error": "Invalid key"}, status_code=401)
    return await call_next(request)


@app.post("/tasks")
def queue_for_transcription(call_audio: UploadFile, call_json: UploadFile):
    metadata = json.loads(call_json.file.read())

    if metadata["call_length"] < float(os.getenv("MIN_CALL_LENGTH", "2")):
        raise HTTPException(status_code=400, detail="Call too short to transcribe")

    raw_audio = tempfile.NamedTemporaryFile(
        delete=False, suffix=f"_{call_audio.filename}"
    )
    while True:
        data = call_audio.file.read(1024 * 1024)
        if not data:
            raw_audio.close()
            break
        raw_audio.write(data)

    audio_url = upload_raw_audio(metadata, raw_audio.name)

    os.unlink(raw_audio.name)

    task = transcribe_task.apply_async(
        queue="transcribe",
        kwargs={
            "metadata": metadata,
            "audio_url": audio_url,
        },
    )
    return JSONResponse({"task_id": task.id}, status_code=201)


@app.get("/tasks/{task_id}")
def get_status(task_id):
    task_result = AsyncResult(task_id, app=celery_app)
    result = {
        "task_id": task_id,
        "task_status": task_result.status,
        "task_result": task_result.result,
    }
    return JSONResponse(result)


@app.get("/config/{filename}")
def get_config(filename):
    if filename not in os.listdir("config"):
        raise HTTPException(status_code=404, detail="Config file not found")

    with open(f"config/{filename}") as config:
        return JSONResponse(json.load(config))

#!/usr/bin/env python3

import json
import os
import tempfile

import sentry_sdk
from celery.result import AsyncResult
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

load_dotenv()

from . import crud, models, schemas, storage, search, notification
from .database import SessionLocal, engine
from .metadata import Metadata
from .transcript import Transcript
from .worker import celery as celery_app
from .worker import transcribe_task, transcribe_from_db_task

sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
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

if os.getenv("POSTGRES_DB") is not None:
    models.Base.metadata.create_all(bind=engine)

app = FastAPI()


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.middleware("http")
async def authenticate(request: Request, call_next):
    api_key = os.getenv("API_KEY", "")

    if api_key and request.headers.get("Authorization", "") != f"Bearer {api_key}":
        return JSONResponse(content={"error": "Invalid key"}, status_code=401)
    return await call_next(request)


@app.post("/tasks")
def queue_for_transcription(
    call_audio: UploadFile,
    call_json: UploadFile,
    whisper_implementation: str | None = None,
):
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

    try:
        audio_url = storage.upload_raw_audio(metadata, raw_audio.name)
    finally:
        os.unlink(raw_audio.name)

    task = transcribe_task.apply_async(
        queue="transcribe",
        kwargs={
            "metadata": metadata,
            "audio_url": audio_url,
            "whisper_implementation": whisper_implementation,
        },
    )
    return JSONResponse({"task_id": task.id}, status_code=201)


@app.get("/tasks/{task_id}")
def get_status(task_id):
    task_result = AsyncResult(task_id, app=celery_app)
    result = {
        "task_id": task_id,
        "task_status": task_result.status,
        "task_result": repr(task_result.result)
        if isinstance(task_result.result, Exception)
        else task_result.result,
    }
    return JSONResponse(result)


@app.get("/calls/", response_model=list[schemas.Call])
def read_calls(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    calls = crud.get_calls(db, skip=skip, limit=limit)
    return calls


@app.get("/calls/{call_id}", response_model=schemas.Call)
def read_call(call_id: int, db: Session = Depends(get_db)):
    db_call = crud.get_call(db, call_id=call_id)
    if db_call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return db_call


@app.post("/calls")
def create_call(
    call_audio: UploadFile,
    call_json: UploadFile,
    db: Session = Depends(get_db),
    whisper_implementation: str | None = None,
):
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

    try:
        audio_url = storage.upload_raw_audio(metadata, raw_audio.name)
    finally:
        os.unlink(raw_audio.name)

    call = schemas.CallCreate(raw_metadata=metadata, raw_audio_url=audio_url)

    db_call = crud.create_call(db=db, call=call)

    task = transcribe_from_db_task.apply_async(
        queue="transcribe",
        kwargs={"id": db_call.id, "whisper_implementation": whisper_implementation},
    )
    return JSONResponse({"task_id": task.id}, status_code=201)


@app.patch("/calls/{call_id}", response_model=schemas.Call)
def update_call(call_id: int, call: schemas.CallUpdate, db: Session = Depends(get_db)):
    db_call = crud.get_call(db, call_id=call_id)
    if db_call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    db_call = crud.update_call(db=db, call=call, db_call=db_call)

    metadata = Metadata(db_call.raw_metadata)  # type: ignore
    transcript = Transcript(db_call.raw_transcript)  # type: ignore

    search_url = search.index_call(
        db_call.id,  # type: ignore
        metadata,
        db_call.raw_audio_url,  # type: ignore
        transcript,
        db_call.geo,  # type: ignore
    )

    notification.send_notifications(
        db_call.raw_audio_url, metadata, transcript, search_url  # type: ignore
    )

    return db_call


@app.get("/config/{filename}")
def get_config(filename):
    if filename not in os.listdir("config"):
        raise HTTPException(status_code=404, detail="Config file not found")

    with open(f"config/{filename}") as config:
        return JSONResponse(json.load(config))

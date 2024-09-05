#!/usr/bin/env python3

import socket
from typing import Annotated, Any
import json
import logging
import os
import subprocess
import sys
import tempfile

from celery.result import AsyncResult
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response, UploadFile
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import sentry_sdk

load_dotenv()

from app.utils.exceptions import before_send
from app.geocoding import geocoding
from app.models.database import SessionLocal, engine
from app.models.metadata import Metadata
from app.models.transcript import Transcript
from app.notifications import notification
from app.search import search
from app.utils import storage
from app.whisper.task import WhisperTask
from app.worker import (
    transcribe_from_db_batch_task,
    transcribe_from_db_task,
    transcribe_task,
    transcribe,
)
from app.worker import celery as celery_app
from app.models import call as call_model, base as base_model

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
        before_send=before_send,
    )

if os.getenv("POSTGRES_DB") is not None:
    base_model.Base.metadata.create_all(bind=engine)

app = FastAPI()

logger = logging.getLogger()
logger.setLevel(os.getenv("UVICORN_LOG_LEVEL", "INFO").upper())
stream_handler = logging.StreamHandler(sys.stdout)
log_formatter = logging.Formatter(
    "%(asctime)s [%(processName)s: %(process)d] [%(threadName)s: %(thread)d] [%(levelname)s] %(name)s: %(message)s"
)
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)

task = WhisperTask()


# Dependency
def get_db():  # type: ignore
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.middleware("http")
async def authenticate(request: Request, call_next) -> Response:  # type: ignore
    api_key = os.getenv("API_KEY", "")

    if (
        request.url.path not in ["/api/call-upload", "/healthz"]
        and api_key
        and request.headers.get("Authorization", "") != f"Bearer {api_key}"
    ):
        return JSONResponse(content={"error": "Invalid key"}, status_code=401)
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> Response:
    if request.url.path == "/api/call-upload":
        try:
            field_name = exc.errors()[0]["loc"][1]
            return Response(f"Incomplete call data: no {field_name}", status_code=417)
        except Exception:
            pass
    return await request_validation_exception_handler(request, exc)


@app.get("/healthz")
def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.post("/api/call-upload")
def create_call_from_sdrtrunk(
    talkgroup: Annotated[int, Form()],
    source: Annotated[int, Form()],
    system: Annotated[int, Form()],
    systemLabel: Annotated[str, Form()],
    dateTime: Annotated[str, Form()],
    key: Annotated[str, Form()],
    frequency: Annotated[int, Form()],
    talkgroupLabel: Annotated[str, Form()],
    talkgroupGroup: Annotated[str, Form()],
    audio: UploadFile,
    db: Session = Depends(get_db),
) -> Response:
    if len(audio.file.read()) <= 44:
        return Response("Incomplete call data: no audio", status_code=417)
    else:
        # Reset file pointer after reading
        audio.file.seek(0)

    if key != os.getenv("API_KEY", None):
        return Response(
            "Invalid API key for system %s talkgroup %s." % (system, talkgroup),
            status_code=401,
        )

    raw_audio = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{audio.filename}")
    while True:
        data = audio.file.read(1024 * 1024)
        if not data:
            raw_audio.close()
            break
        raw_audio.write(data)

    cmd = [
        "ffprobe",
        "-i",
        raw_audio.file.name,
        "-show_entries",
        "format=duration",
        "-v",
        "quiet",
        "-of",
        "csv=p=0",
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    result.check_returncode()
    duration = float(result.stdout.decode("utf-8").strip())

    if duration < float(os.getenv("MIN_CALL_LENGTH", "2")):
        raise HTTPException(status_code=400, detail="Call too short to transcribe")

    start_time = int(dateTime)
    stop_time = round(start_time + duration)

    metadata: Metadata = {
        "short_name": systemLabel,
        "start_time": start_time,
        "stop_time": stop_time,
        "call_length": duration,
        "talkgroup": talkgroup,
        "talkgroup_group": talkgroupGroup,
        "talkgroup_tag": talkgroupLabel,
        "talkgroup_group_tag": "",
        "talkgroup_description": "",
        "audio_type": "digital",
        "emergency": 0,
        "encrypted": 0,
        "freq": frequency,
        "freqList": [
            {"freq": frequency, "time": start_time, "pos": 0.0, "len": duration}
        ],
        "srcList": [
            {
                "src": source,
                "time": start_time,
                "pos": 0.0,
                "emergency": 0,
                "signal_system": "",
                "tag": "",
                "transcript_prompt": "",
            }
        ],
    }

    try:
        audio_url = storage.upload_raw_audio(metadata, raw_audio.name)
    finally:
        os.unlink(raw_audio.name)

    call = call_model.CallCreateSchema(
        raw_metadata=dict(metadata), raw_audio_url=audio_url
    )

    db_call = call_model.create_call(db=db, call=call)

    if os.getenv("WHISPER_IMPLEMENTATION") == "whispers2t":
        transcribe_from_db_batch_task.apply_async(
            queue="transcribe",
            kwargs={"id": db_call.id},
        )
    else:
        transcribe_from_db_task.apply_async(
            queue="transcribe",
            kwargs={"id": db_call.id},
        )

    return Response("Call imported successfully.", status_code=200)


@app.post("/tasks")
def queue_for_transcription(
    call_audio: UploadFile,
    call_json: UploadFile,
    whisper_implementation: str | None = None,
) -> JSONResponse:
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
def get_status(task_id: str) -> JSONResponse:
    task_result = AsyncResult(task_id, app=celery_app)  # type: ignore
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


@app.get("/calls/", response_model=list[call_model.CallSchema])
def read_calls(
    skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
) -> list[call_model.Call]:
    calls = call_model.get_calls(db, skip=skip, limit=limit)
    return calls


@app.get("/calls/{call_id}", response_model=call_model.CallSchema)
def read_call(call_id: int, db: Session = Depends(get_db)) -> call_model.Call:
    db_call = call_model.get_call(db, call_id=call_id)
    if db_call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return db_call


@app.post("/calls")
def create_call(
    call_json: UploadFile,
    call_audio_url: Annotated[str, Form()] | None = None,
    call_audio: UploadFile | None = None,
    db: Session = Depends(get_db),
    whisper_implementation: str | None = None,
    batch: bool = False,
) -> JSONResponse:
    metadata = json.loads(call_json.file.read())

    if metadata["call_length"] < float(os.getenv("MIN_CALL_LENGTH", "2")):
        raise HTTPException(status_code=400, detail="Call too short to transcribe")

    if call_audio:
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
    elif call_audio_url:
        audio_url = call_audio_url
    else:
        raise HTTPException(status_code=400, detail="No audio provided")

    call = call_model.CallCreateSchema(raw_metadata=metadata, raw_audio_url=audio_url)

    db_call = call_model.create_call(db=db, call=call)

    task: AsyncResult[Any]

    if batch:
        if os.getenv("WHISPER_IMPLEMENTATION") != "whispers2t":
            raise HTTPException(
                status_code=400,
                detail="Batch transcription only supported with whispers2t",
            )
        task = transcribe_from_db_batch_task.apply_async(
            queue="transcribe",
            kwargs={"id": db_call.id},
        )
    else:
        task = transcribe_from_db_task.apply_async(
            queue="transcribe",
            kwargs={"id": db_call.id, "whisper_implementation": whisper_implementation},
        )
    return JSONResponse({"task_id": task.id}, status_code=201)


@app.patch("/calls/{call_id}", response_model=call_model.CallSchema)
def update_call(
    call_id: int, call: call_model.CallUpdateSchema, db: Session = Depends(get_db)
) -> call_model.Call:
    db_call = call_model.get_call(db, call_id=call_id)
    if db_call is None:
        raise HTTPException(status_code=404, detail="Call not found")

    metadata = Metadata(db_call.raw_metadata)  # type: ignore
    transcript = Transcript(call.raw_transcript)  # type: ignore
    call.geo = geocoding.lookup_geo(metadata, transcript)

    db_call = call_model.update_call(db=db, call=call, db_call=db_call)

    search_url = search.index_call(
        db_call.id,  # type: ignore
        metadata,
        db_call.raw_audio_url,  # type: ignore
        transcript,
        db_call.geo,  # type: ignore
    )

    notification.send_notifications(
        db_call.raw_audio_url,  # type: ignore
        metadata,
        transcript,
        db_call.geo,  # type: ignore
        search_url,  # type: ignore
    )

    search.make_next_index()

    return db_call


@app.post("/transcribe")
def transcribe_audio(
    call_audio: UploadFile,
    call_json: UploadFile,
    prompt: Annotated[str | None, Form()] = None,
    whisper_implementation: str | None = None,
) -> JSONResponse:
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

    audio_file = raw_audio.name

    try:
        transcript = transcribe(
            task.model(whisper_implementation),
            metadata,
            audio_file,
            prompt=prompt if prompt else "",
        )
    finally:
        try:
            os.unlink(audio_file)
        except OSError:
            pass

    if transcript:
        return JSONResponse(
            {"raw_transcript": transcript.transcript, "transcript": transcript.txt}
        )
    raise HTTPException(status_code=500, detail="Transcription failed, no transcript")


@app.get("/config/{filename}")
def get_config(filename: str) -> JSONResponse:
    if filename not in os.listdir("config"):
        raise HTTPException(status_code=404, detail="Config file not found")

    with open(f"config/{filename}") as config:
        return JSONResponse(json.load(config))


@app.post("/haproxy")
def add_server_to_haproxy(
    name: Annotated[str, Form()],
    server: Annotated[str, Form()],
    port: Annotated[int, Form()],
) -> JSONResponse:
    def _is_valid_server(server: str) -> bool:
        try:
            socket.inet_aton(server)
            return True
        except socket.error:
            return False

    def _validate_haproxy_values(name: str, server: str, port: int) -> bool:
        if not name.isalnum():
            return False
        if not server or not server.strip() or not _is_valid_server(server):
            return False
        if not isinstance(port, int) or port <= 0 or port > 65535:
            return False
        return True

    if not _validate_haproxy_values(name, server, port):
        raise HTTPException(status_code=400, detail="Invalid values for HAProxy")
    _send_haproxy_command(f"add server webservers/{name} {server}:{port} check")
    return JSONResponse({"status": "ok"})


@app.delete("/haproxy")
def remove_server_from_haproxy(
    name: Annotated[str, Form()],
) -> JSONResponse:
    if not name.isalnum():
        raise HTTPException(status_code=400, detail="Invalid values for HAProxy")
    _send_haproxy_command(f"del server webservers/{name}")
    return JSONResponse({"status": "ok"})


def _send_haproxy_command(command: str) -> list[str]:
    try:
        haproxy_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        haproxy_socket.settimeout(1)
        haproxy_ip = os.getenv("HAPROXY_STATS_ADDRESS")
        if haproxy_ip is not None:
            haproxy_socket.connect(haproxy_ip)
        else:
            raise ValueError("HAPROXY_STATS_ADDRESS environment variable is not set.")
        logging.debug(f"Running HAProxy command: {command}")
        haproxy_socket.send((command + "\n").encode())

        file_handler = haproxy_socket.makefile()
        rdata = file_handler.read().splitlines()
    finally:
        haproxy_socket.close()

    return rdata[:-1]

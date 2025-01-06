#!/usr/bin/env python3

from datetime import datetime
from typing import Annotated, Generator
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
from sqlmodel import Session, select, func
import sentry_sdk

load_dotenv()

from app.models.transcript import Transcript
from app.search.helpers import get_default_index_name
from app.utils.exceptions import before_send
from app.models.database import engine
from app.models.metadata import Metadata
from app.utils import storage
from app import worker
from app.models import models

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

app = FastAPI()

logger = logging.getLogger()
logger.setLevel(os.getenv("UVICORN_LOG_LEVEL", "INFO").upper())
stream_handler = logging.StreamHandler(sys.stdout)
log_formatter = logging.Formatter(
    "%(asctime)s [%(processName)s: %(process)d] [%(threadName)s: %(thread)d] [%(levelname)s] %(name)s: %(message)s"
)
stream_handler.setFormatter(log_formatter)
logger.addHandler(stream_handler)


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


@app.middleware("http")
async def authenticate(request: Request, call_next) -> Response:
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

    call = models.CallCreate(raw_metadata=metadata, raw_audio_url=audio_url)

    db_call = models.create_call(db=db, call=call)

    if "digital" in metadata["audio_type"]:
        from app.radio.digital import build_transcribe_options
    elif metadata["audio_type"] == "analog":
        from app.radio.analog import build_transcribe_options
    else:
        raise HTTPException(
            status_code=400, detail=f"Audio type {metadata['audio_type']} not supported"
        )

    worker.queue_task(
        audio_url,
        metadata,
        build_transcribe_options(metadata),
        whisper_implementation=None,
        id=db_call.id,
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


@app.get("/tasks/{task_id}")
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


@app.get("/calls/", response_model=models.CallsPublic)
def read_calls(
    skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
) -> models.CallsPublic:
    count_statement = select(func.count()).select_from(models.Call)
    count = db.exec(count_statement).one()

    statement = select(models.Call).offset(skip).limit(limit)
    calls = db.exec(statement).all()

    return models.CallsPublic(data=calls, count=count)


@app.get("/calls/{call_id}", response_model=models.CallPublic)
def read_call(call_id: int, db: Session = Depends(get_db)) -> models.Call:
    db_call = db.get(models.Call, call_id)
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

    if "digital" in metadata["audio_type"]:
        from app.radio.digital import build_transcribe_options
    elif metadata["audio_type"] == "analog":
        from app.radio.analog import build_transcribe_options
    else:
        raise HTTPException(
            status_code=400, detail=f"Audio type {metadata['audio_type']} not supported"
        )

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

    start_time = datetime.fromtimestamp(metadata["start_time"])

    call = models.CallCreate(
        raw_metadata=metadata, raw_audio_url=audio_url, start_time=start_time
    )

    db_call = models.create_call(db=db, call=call)

    task = worker.queue_task(
        audio_url,
        metadata,
        build_transcribe_options(metadata),
        whisper_implementation,
        db_call.id,
    )

    return JSONResponse(
        {"task_id": task.id},
        status_code=201,
    )


@app.patch("/calls/{call_id}", response_model=models.CallPublic)
def update_call(
    call_id: int, call: models.CallUpdate, db: Session = Depends(get_db)
) -> models.Call:
    db_call = db.get(models.Call, call_id)
    if db_call is None:
        raise HTTPException(status_code=404, detail="Call not found")

    if call.raw_transcript and not call.transcript_plaintext:
        transcript = Transcript(call.raw_transcript)
        call.transcript_plaintext = transcript.txt_nosrc

    return models.update_call(db=db, call=call, db_call=db_call)


@app.get("/talkgroups")
def talkgroups(db: Session = Depends(get_db)) -> JSONResponse:
    tgs = models.get_talkgroups(db)
    return JSONResponse({"talkgroups": tgs})


@app.get("/config/{filename}")
def get_config(filename: str) -> JSONResponse:
    if filename not in os.listdir("config"):
        raise HTTPException(status_code=404, detail="Config file not found")

    with open(f"config/{filename}") as config:
        return JSONResponse(json.load(config))

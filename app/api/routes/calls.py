from datetime import datetime
from typing import Annotated
import json
import os
import tempfile

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import JSONResponse
from sqlmodel import Session, select, func

from app.api.depends import get_db
from app.models.transcript import Transcript
from app.utils import storage
from app import worker
from app.models import models


router = APIRouter()


@router.get("/calls/", response_model=models.CallsPublic)
def read_calls(
    skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
) -> models.CallsPublic:
    count_statement = select(func.count()).select_from(models.Call)
    count = db.exec(count_statement).one()

    statement = select(models.Call).offset(skip).limit(limit)
    calls = db.exec(statement).all()

    return models.CallsPublic(data=calls, count=count)


@router.get("/calls/{call_id}", response_model=models.CallPublic)
def read_call(call_id: int, db: Session = Depends(get_db)) -> models.Call:
    db_call = db.get(models.Call, call_id)
    if db_call is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return db_call


@router.post("/calls")
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


@router.patch("/calls/{call_id}", response_model=models.CallPublic)
def update_call(
    call_id: int, call: models.CallUpdate, db: Session = Depends(get_db)
) -> models.Call:
    db_call = db.get(models.Call, call_id)
    if db_call is None:
        raise HTTPException(status_code=404, detail="Call not found")

    if call.raw_transcript and not call.transcript_plaintext:
        transcript = Transcript(call.raw_transcript)
        call.transcript_plaintext = transcript.txt

    return models.update_call(db=db, call=call, db_call=db_call)

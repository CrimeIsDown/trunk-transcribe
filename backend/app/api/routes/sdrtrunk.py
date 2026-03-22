#!/usr/bin/env python3

from typing import Annotated
import os
import subprocess
import tempfile

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Response,
    UploadFile,
)
from sqlmodel import Session

from app.api.depends import get_db
from app.models.metadata import Metadata
from app.utils import storage
from app import worker
from app.models import models


router = APIRouter()


@router.post("/api/call-upload")
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

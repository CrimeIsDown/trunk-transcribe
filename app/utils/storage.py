import os
from datetime import datetime
from functools import lru_cache
from mimetypes import guess_type
import tempfile

import boto3
import pytz
from botocore.config import Config
from datauri import DataURI
import requests

from .conversion import convert_to_mp3, convert_to_wav
from app.models.metadata import Metadata


@lru_cache()
def get_storage_client():  # type: ignore
    return boto3.resource(
        service_name="s3",
        endpoint_url=os.getenv("S3_ENDPOINT"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        config=Config(
            signature_version="s3v4",
        ),
    )


def upload_file(filename: str, remote_path: str | None = None) -> str:
    mime_type = guess_type(filename)
    if remote_path is None:
        remote_path = os.path.basename(filename)
    get_storage_client().Bucket(os.getenv("S3_BUCKET")).upload_file(
        Filename=filename,
        Key=remote_path,
        ExtraArgs={"ACL": "public-read", "ContentType": mime_type[0]},
    )
    return f"{os.getenv('S3_PUBLIC_URL', '')}/{remote_path}"


def upload_raw_audio(metadata: Metadata, audio_file: str) -> str:
    start_time = datetime.fromtimestamp(metadata["start_time"], tz=pytz.UTC)
    uploaded_audio_path = (
        start_time.strftime("%Y/%m/%d/%H/%Y%m%d_%H%M%S")
        + f"_{metadata['short_name']}_{metadata['talkgroup']}.mp3"
    )

    mp3 = convert_to_mp3(audio_file, metadata)
    url = upload_file(mp3, uploaded_audio_path)
    os.unlink(mp3)

    return url


def fetch_audio(audio_url: str) -> str:
    mp3_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    if audio_url.startswith("data:"):
        uri = DataURI(audio_url)
        mp3_file.write(uri.data)  # type: ignore
        mp3_file.close()
    else:
        # Do this replacement so we can use the correct URL inside of Docker
        localhost_url = "http://127.0.0.1:9000"
        if audio_url.startswith(localhost_url):
            audio_url = audio_url.replace(
                localhost_url, os.getenv("S3_ENDPOINT", "http://minio:9000")
            )
        with requests.get(audio_url, stream=True) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                mp3_file.write(chunk)
            mp3_file.close()

    try:
        audio_file = convert_to_wav(mp3_file.name)
    finally:
        os.unlink(mp3_file.name)

    return audio_file

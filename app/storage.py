from functools import lru_cache
import os
import boto3
from botocore.config import Config


@lru_cache()
def get_storage_client():
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
    if remote_path is None:
        remote_path = os.path.basename(filename)
    get_storage_client().Bucket(os.getenv("S3_BUCKET")).upload_file(
        Filename=filename, Key=remote_path, ExtraArgs={"ACL": "public-read"}
    )
    return f"{os.getenv('S3_PUBLIC_URL', '')}/{remote_path}"
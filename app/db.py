import json
import os

import psycopg
import psycopg_pool

from app.metadata import Metadata
from app.transcript import Transcript


def build_connection_string() -> str:
    return " ".join(
        [
            f"{k}={v}"
            for k, v in {
                "host": os.getenv("POSTGRES_HOST"),
                "dbname": os.getenv("POSTGRES_DB"),
                "user": os.getenv("POSTGRES_USER"),
                "password": os.getenv("POSTGRES_PASSWORD"),
            }.items()
        ]
    )


def create_pool() -> psycopg_pool.ConnectionPool:
    return psycopg_pool.ConnectionPool(build_connection_string())


def connect() -> psycopg.Connection:
    return psycopg.connect(build_connection_string())


def insert(
    conn: psycopg.Connection,
    metadata: Metadata,
    raw_audio_url: str,
    transcript: Transcript,
):
    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO calls (raw_metadata, raw_audio_url, raw_transcript) VALUES (%s, %s, %s)",
            (json.dumps(metadata), raw_audio_url, transcript.json),
        )

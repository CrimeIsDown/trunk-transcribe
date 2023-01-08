import datetime
import json
import logging
import os
import typesense
from app.conversion import convert_to_mp3

from app.digital import parse_radio_id
from app.storage import upload_file

search_client = None


def get_search_client() -> typesense.Client:
    global search_client
    if not search_client:
        host = os.getenv("TYPESENSE_HOST", "localhost")
        port = os.getenv("TYPESENSE_PORT", "8108")
        protocol = os.getenv("TYPESENSE_PROTO", "http")
        api_key = os.getenv("TYPESENSE_API_KEY")

        search_client = typesense.Client(
            {
                "nodes": [
                    {
                        "host": host,  # For Typesense Cloud use xxx.a1.typesense.net
                        "port": port,  # For Typesense Cloud use 443
                        "protocol": protocol,  # For Typesense Cloud use https
                    }
                ],
                "api_key": api_key,
                "connection_timeout_seconds": 2,
            }
        )
    return search_client


def index(metadata: dict, audio_file: str, transcript: str):
    client = get_search_client()

    collection_name = "calls"

    calls_schema = {
        "name": collection_name,
        "fields": [
            {"name": "freq", "type": "int32"},
            {"name": "start_time", "type": "int64", "facet": True},
            {"name": "stop_time", "type": "int64"},
            {"name": "call_length", "type": "int32"},
            {"name": "talkgroup", "type": "int32", "facet": True},
            {"name": "talkgroup_tag", "type": "string", "facet": True},
            {"name": "talkgroup_description", "type": "string", "facet": True},
            {"name": "talkgroup_group_tag", "type": "string", "facet": True},
            {"name": "talkgroup_group", "type": "string", "facet": True},
            {"name": "audio_type", "type": "string", "facet": True},
            {"name": "short_name", "type": "string", "facet": True},
            {"name": "srcList", "type": "string[]", "facet": True},
            {"name": "transcript", "type": "string"},
            {
                "name": "raw_metadata",
                "type": "string",
                "index": False,
                "optional": True,
            },
            {
                "name": "raw_audio_url",
                "type": "string",
                "index": False,
                "optional": True,
            },
        ],
        "default_sorting_field": "stop_time",
    }

    if "calls" not in [
        collection["name"] for collection in client.collections.retrieve()
    ]:
        client.collections.create(calls_schema)

    srcList = [
        src["tag"]
        if len(src["tag"])
        else parse_radio_id(str(src["src"]), metadata["short_name"])[0]
        for src in metadata["srcList"]
    ]

    start_time = datetime.datetime.fromtimestamp(metadata["start_time"])
    uploaded_audio_path = (
        start_time.strftime("%Y/%m/%d/%H/%Y%m%d_%H%M%S")
        + f"_{metadata['short_name']}_{metadata['talkgroup']}.mp3"
    )
    raw_audio_url = upload_file(convert_to_mp3(audio_file), uploaded_audio_path)

    doc = {
        "freq": metadata["freq"],
        "start_time": metadata["start_time"],
        "stop_time": metadata["stop_time"],
        "call_length": metadata["call_length"],
        "talkgroup": metadata["talkgroup"],
        "talkgroup_tag": metadata["talkgroup_tag"],
        "talkgroup_description": metadata["talkgroup_description"].split("|")[0],
        "talkgroup_group_tag": metadata["talkgroup_group_tag"],
        "talkgroup_group": metadata["talkgroup_group"],
        "audio_type": metadata["audio_type"],
        "short_name": metadata["short_name"],
        "srcList": srcList,
        "transcript": transcript,
        "raw_metadata": json.dumps(metadata),
        "raw_audio_url": raw_audio_url,
    }

    logging.debug(f"Sending document to be indexed: {str(doc)}")

    client.collections[collection_name].documents.create(doc)  # type: ignore

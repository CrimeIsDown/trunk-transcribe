import json
import logging
import os
from hashlib import sha256

from meilisearch import Client
from meilisearch.errors import MeiliSearchApiError
from meilisearch.index import Index
from meilisearch.models.task import TaskInfo

index = None

ID = "id"
RAW_METADATA = "raw_metadata"
RAW_AUDIO_URL = "raw_audio_url"


def get_client() -> Client:
    url = os.getenv("MEILI_URL", "http://127.0.0.1:7700")
    api_key = os.getenv("MEILI_MASTER_KEY")
    return Client(url=url, api_key=api_key)


def get_index() -> Index:
    global index
    if not index:
        client = get_client()
        index_name = os.getenv("MEILI_INDEX", "calls")
        index = client.index(index_name)
        try:
            index.fetch_info()
        except MeiliSearchApiError:
            index = create_index(client, index_name)

    return index


def build_document(
    metadata: dict, raw_audio_url: str, transcript: str, id: str | None = None
) -> dict:
    srcList = set()
    for src in metadata["srcList"]:
        if len(src["tag"]):
            srcList.add(src["tag"])
        srcList.add(str(src["src"]))

    raw_metadata = json.dumps(metadata)
    if not id:
        id = sha256(raw_metadata.encode("utf-8")).hexdigest()

    return {
        "freq": metadata["freq"],
        "start_time": metadata["start_time"],
        "stop_time": metadata["stop_time"],
        "call_length": metadata["call_length"],
        "talkgroup": metadata["talkgroup"],
        "talkgroup_tag": metadata["talkgroup_tag"],
        "talkgroup_description": metadata["talkgroup_description"],
        "talkgroup_group_tag": metadata["talkgroup_group_tag"],
        "talkgroup_group": metadata["talkgroup_group"],
        "audio_type": metadata["audio_type"],
        "short_name": metadata["short_name"],
        "srcList": list(srcList),
        "transcript": transcript,
        RAW_METADATA: raw_metadata,
        RAW_AUDIO_URL: raw_audio_url,
        ID: id,
    }


def index_call(
    metadata: dict, raw_audio_url: str, transcript: str, id: str | None = None
) -> TaskInfo:
    doc = build_document(metadata, raw_audio_url, transcript, id)

    logging.debug(f"Sending document to be indexed: {str(doc)}")

    return get_index().add_documents([doc])


def create_index(client: Client, index_name: str) -> Index:
    client.create_index(index_name)
    index = client.index(index_name)

    index.update_settings(
        {
            "searchableAttributes": [
                "transcript",
                "srcList",
            ],
            "filterableAttributes": [
                "start_time",
                "talkgroup",
                "talkgroup_tag",
                "talkgroup_description",
                "talkgroup_group_tag",
                "talkgroup_group",
                "audio_type",
                "short_name",
                "srcList",
            ],
            "sortableAttributes": [
                "start_time",
            ],
            "rankingRules": [
                "sort",
                "words",
                "typo",
                "proximity",
                "attribute",
                "exactness",
            ],
        }
    )

    return index

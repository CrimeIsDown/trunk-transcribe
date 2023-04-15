import json
import logging
import os
from hashlib import sha256

from meilisearch import Client
from meilisearch.errors import MeilisearchError, MeilisearchApiError
from meilisearch.index import Index
from meilisearch.models.task import TaskInfo

from app.metadata import Metadata, SearchableMetadata
from app.transcript import Transcript

client = None


class Document(SearchableMetadata):
    units: list[str]
    radios: list[str]
    srcList: list[str]
    transcript: str
    transcript_plaintext: str
    raw_transcript: str
    raw_metadata: str
    raw_audio_url: str
    id: str


def get_client() -> Client:
    global client
    if not client:
        url = os.getenv("MEILI_URL", "http://127.0.0.1:7700")
        api_key = os.getenv("MEILI_MASTER_KEY")
        client = Client(url=url, api_key=api_key)
    return client


def get_default_index_name() -> str:
    return os.getenv("MEILI_INDEX", "calls")


def get_index(index_name: str) -> Index:
    client = get_client()
    index = client.index(index_name)
    try:
        index.fetch_info()
    except MeilisearchApiError as e:
        if e.code == "index_not_found":
            index = create_or_update_index(client, index_name)
        else:
            raise e

    return index


def build_document(
    metadata: Metadata,
    raw_audio_url: str,
    transcript: Transcript,
    id: str | None = None,
) -> Document:
    srcList = set()
    units = set()
    radios = set()
    for src in metadata["srcList"]:
        if src["src"] <= 0:
            continue
        if len(src["tag"]):
            units.add(src["tag"])
            srcList.add(src["tag"])
        else:
            srcList.add(str(src["src"]))
        radios.add(str(src["src"]))

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
        "units": list(units),
        "radios": list(radios),
        "transcript": transcript.html,
        "transcript_plaintext": transcript.txt,
        "raw_transcript": transcript.json,
        "raw_metadata": raw_metadata,
        "raw_audio_url": raw_audio_url,
        "id": id,
    }


def index_call(
    metadata: Metadata,
    raw_audio_url: str,
    transcript: Transcript,
    id: str | None = None,
    index_name: str | None = None,
) -> TaskInfo:
    doc = build_document(metadata, raw_audio_url, transcript, id)

    logging.debug(f"Sending document to be indexed: {str(doc)}")

    if not index_name:
        index_name = get_default_index_name()

    try:
        return get_index(index_name).add_documents([doc])  # type: ignore
    # Raise a different exception because of https://github.com/celery/celery/issues/6990
    except MeilisearchApiError as err:
        raise MeilisearchError(str(err))


def create_or_update_index(
    client: Client, index_name: str, create: bool = True
) -> Index:
    if create:
        client.create_index(index_name)
    index = client.index(index_name)

    index.update_settings(
        {
            "searchableAttributes": [
                "transcript_plaintext",
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
                "units",
                "radios",
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

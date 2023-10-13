import json
import logging
import os
from hashlib import sha256
from itertools import chain, starmap
from time import sleep
from urllib.parse import urlencode

from meilisearch import Client
from meilisearch.errors import MeilisearchApiError, MeilisearchError
from meilisearch.index import Index

from app.metadata import Metadata, SearchableMetadata
from app.transcript import Transcript
from app.geocoding import add_geo


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
    _geo: dict[str, float]
    geo_formatted_address: str


def get_client(
    url: str | None = None, api_key: str | None = None
) -> Client:  # pragma: no cover
    if not url:
        url = os.getenv("MEILI_URL", "http://127.0.0.1:7700")
    if not api_key:
        api_key = os.getenv("MEILI_MASTER_KEY")
    return Client(url=url, api_key=api_key)


def get_default_index_name() -> str:  # pragma: no cover
    return os.getenv("MEILI_INDEX", "calls")


def get_index(index_name: str) -> Index:  # pragma: no cover
    if "@" in index_name:
        parts = index_name.split("@")
        index_name = parts[0]
        url = parts[1]
        client = get_client(url)
    else:
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


# TODO: write tests
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

    doc = {
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

    doc = add_geo(doc, metadata, transcript)

    return doc  # type: ignore


def build_search_url(document: Document, index_name: str) -> str:
    base_url = os.getenv("SEARCH_UI_URL")
    if not base_url:
        return ""
    params = {
        index_name: {
            "sortBy": index_name + ":start_time:desc",
            "hitsPerPage": 60,
            "refinementList": {"talkgroup_tag": [document["talkgroup_tag"]]},
            "range": {
                "start_time": str(document["start_time"] - 60 * 20)
                + ":"
                + str(document["start_time"] + 60 * 10)
            },
        }
    }
    hash = "hit-" + document["id"]

    encoded_params = urlencode(flatten_dict(params))

    return f"{base_url}?{encoded_params}#{hash}"


def index_call(
    metadata: Metadata,
    raw_audio_url: str,
    transcript: Transcript,
    id: str | None = None,
    index_name: str | None = None,
) -> str:  # pragma: no cover
    doc = build_document(metadata, raw_audio_url, transcript, id)

    logging.debug(f"Sending document to be indexed: {str(doc)}")

    if not index_name:
        index_name = get_default_index_name()

    try:
        get_index(index_name).add_documents([doc])  # type: ignore
    # Raise a different exception because of https://github.com/celery/celery/issues/6990
    except MeilisearchApiError as err:
        raise MeilisearchError(str(err))

    return build_search_url(doc, index_name)


def create_or_update_index(
    client: Client, index_name: str, create: bool = True
) -> Index:  # pragma: no cover
    if create:
        client.create_index(index_name)
        sleep(2)  # Wait for index to be created
    index = client.index(index_name)

    current_settings = index.get_settings()

    desired_settings = {
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
            "_geo",
        ],
        "sortableAttributes": [
            "start_time",
            "_geo",
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

    for key, value in desired_settings.copy().items():
        if current_settings[key] == value:
            del desired_settings[key]

    logging.info(f"Updating settings: {str(desired_settings)}")
    task = index.update_settings(desired_settings)
    logging.info(f"Waiting for settings update task {task.task_uid} to complete...")
    while client.get_task(task.task_uid).status not in [
        "succeeded",
        "failed",
        "canceled",
    ]:
        sleep(2)

    return index


def flatten_dict(dictionary):
    """Flatten a nested dictionary structure"""

    def unpack(parent_key, parent_value):
        """Unpack one level of nesting in a dictionary"""
        try:
            items = parent_value.items()
        except AttributeError:
            # parent_value was not a dict, no need to flatten
            yield (parent_key, parent_value)
        else:
            for key, value in items:
                if type(value) == list:
                    for k, v in enumerate(value):
                        yield (parent_key + "[" + key + "]" + "[" + str(k) + "]", v)
                else:
                    yield (parent_key + "[" + key + "]", value)

    while True:
        # Keep unpacking the dictionary until all value's are not dictionary's
        dictionary = dict(chain.from_iterable(starmap(unpack, dictionary.items())))
        if not any(isinstance(value, dict) for value in dictionary.values()):
            break
    return dictionary

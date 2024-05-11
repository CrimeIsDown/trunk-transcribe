import datetime
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

from .metadata import Metadata, SearchableMetadata
from .transcript import Transcript
from .geocoding import GeoResponse


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


def get_default_index_name(
    time: datetime.datetime | None = None,
) -> str:  # pragma: no cover
    index_name = os.getenv("MEILI_INDEX", "calls")
    if os.getenv("MEILI_INDEX_SPLIT_BY_MONTH") == "true":
        if not time:
            time = datetime.datetime.now()
        index_name += time.strftime("_%Y_%m")
    return index_name


def make_next_index():
    future_index_name = get_default_index_name(
        datetime.datetime.now() + datetime.timedelta(hours=1)
    )
    if get_default_index_name() != future_index_name:
        client = get_client()
        create_or_update_index(client, future_index_name)


# TODO: write tests
def build_document(
    id: str | int,
    metadata: Metadata,
    raw_audio_url: str,
    transcript: Transcript,
    geo: GeoResponse | None = None,
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
        "talkgroup_hierarchy": {
            "lvl0": metadata["short_name"],
            "lvl1": metadata["short_name"] + " > " + metadata["talkgroup_group"],
            "lvl2": metadata["short_name"]
            + " > "
            + metadata["talkgroup_group"]
            + " > "
            + metadata["talkgroup_tag"],
        },
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

    if geo:
        doc.update(
            {"_geo": geo["geo"], "geo_formatted_address": geo["geo_formatted_address"]}
        )

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
    hash = "hit-" + str(document["id"])

    encoded_params = urlencode(flatten_dict(params))

    return f"{base_url}?{encoded_params}#{hash}"


def index_call(
    id: int | str,
    metadata: Metadata,
    raw_audio_url: str,
    transcript: Transcript,
    geo: GeoResponse | None = None,
    index_name: str | None = None,
) -> str:  # pragma: no cover
    doc = build_document(id, metadata, raw_audio_url, transcript, geo)

    logging.debug(f"Sending document to be indexed: {str(doc)}")

    if not index_name:
        call_time = datetime.datetime.fromtimestamp(metadata["start_time"])
        index_name = get_default_index_name(call_time)

    client = get_client()

    try:
        client.index(index_name).add_documents([doc])  # type: ignore
    except MeilisearchApiError as err:
        # Raise a different exception because of https://github.com/celery/celery/issues/6990
        raise MeilisearchError(str(err))

    return build_search_url(doc, index_name)


def create_or_update_index(
    client: Client, index_name: str
) -> Index:  # pragma: no cover
    index = client.index(index_name)

    try:
        current_settings = index.get_settings()
    except MeilisearchApiError as err:
        if err.code == "index_not_found":
            current_settings = {}
        else:
            raise err

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
            "talkgroup_hierarchy.lvl0",
            "talkgroup_hierarchy.lvl1",
            "talkgroup_hierarchy.lvl2",
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
        if key in current_settings and current_settings[key] == value:
            del desired_settings[key]

    # If all the settings match, return the index
    if not desired_settings:
        return index

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

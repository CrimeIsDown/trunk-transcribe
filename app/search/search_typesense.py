import datetime
import json
import logging
import os
from typing import Optional
from urllib.parse import urlparse

import typesense
from typesense.exceptions import ObjectNotFound, TypesenseClientError

from app.models.metadata import Metadata, SearchableMetadata
from app.models.transcript import Transcript
from app.geocoding.geocoding import GeoResponse
from app.search.url import encode_params

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
    url: str | None = None, api_key: str | None = None, timeout: int = 2
) -> typesense.Client:  # pragma: no cover
    if not url:
        url = os.getenv("TYPESENSE_URL", "http://typesense:8108")
    if not api_key:
        api_key = os.getenv("TYPESENSE_API_KEY")

    parsed_url = urlparse(url)
    host = parsed_url.hostname
    port = parsed_url.port or "8108"
    protocol = parsed_url.scheme or "http"

    return typesense.Client(
        {
            "nodes": [{"host": host, "port": port, "protocol": protocol}],
            "api_key": api_key,
            "connection_timeout_seconds": timeout,
        }
    )


def get_default_index_name(
    time: datetime.datetime | None = None,
) -> str:  # pragma: no cover
    index_name = os.getenv("MEILI_INDEX", "calls")
    if os.getenv("MEILI_INDEX_SPLIT_BY_MONTH") == "true":
        if not time:
            time = datetime.datetime.now()
        index_name += time.strftime("_%Y_%m")
    return index_name


def make_next_index(client: Optional[typesense.Client] = None) -> None:
    future_index_name = get_default_index_name(
        datetime.datetime.now() + datetime.timedelta(hours=1)
    )
    if get_default_index_name() != future_index_name:
        if not client:
            client = get_client()
        create_or_update_index(client, future_index_name)


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
        "talkgroup_hierarchy.lvl0": metadata["short_name"],
        "talkgroup_hierarchy.lvl1": metadata["short_name"]
        + " > "
        + metadata["talkgroup_group"],
        "talkgroup_hierarchy.lvl2": metadata["short_name"]
        + " > "
        + metadata["talkgroup_group"]
        + " > "
        + metadata["talkgroup_tag"],
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
        "id": str(id),
    }

    if geo:
        doc.update(
            {
                "_geo": [geo["geo"]["lat"], geo["geo"]["lng"]],
                "geo_formatted_address": geo["geo_formatted_address"],
            }
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

    encoded_params = encode_params(params)

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
        client.collections[index_name].documents.create(doc)  # type: ignore
    except TypesenseClientError as err:
        raise Exception(str(err))

    return build_search_url(doc, index_name)


def create_or_update_index(
    client: typesense.Client, index_name: str
) -> None:  # pragma: no cover
    schema = {
        "name": index_name,
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
            {"name": "talkgroup_hierarchy.lvl0", "type": "string", "facet": True},
            {"name": "talkgroup_hierarchy.lvl1", "type": "string", "facet": True},
            {"name": "talkgroup_hierarchy.lvl2", "type": "string", "facet": True},
            {"name": "audio_type", "type": "string", "facet": True},
            {"name": "short_name", "type": "string", "facet": True},
            {"name": "srcList", "type": "string[]", "facet": True},
            {"name": "units", "type": "string[]", "facet": True},
            {"name": "radios", "type": "string[]", "facet": True},
            {"name": "transcript", "type": "string"},
            {"name": "transcript_plaintext", "type": "string"},
            {"name": "raw_transcript", "type": "string"},
            {"name": "raw_metadata", "type": "string"},
            {"name": "raw_audio_url", "type": "string"},
            {"name": "geo_formatted_address", "type": "string", "optional": True},
            {"name": "_geo", "type": "geopoint", "optional": True},
        ],
        "default_sorting_field": "start_time",
    }

    try:
        client.collections[index_name].retrieve()  # type: ignore
    except ObjectNotFound:
        client.collections.create(schema)

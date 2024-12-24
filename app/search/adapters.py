import datetime
import json
import logging
import os
from abc import ABC, abstractmethod
from time import sleep
from urllib.parse import urlparse

import typesense
from typesense.collections import Collection
import meilisearch
from meilisearch.errors import MeilisearchApiError, MeilisearchError
from meilisearch.index import Index
from typesense.exceptions import ObjectNotFound, TypesenseClientError

from app.geocoding.geocoding import GeoResponse
from app.models.metadata import Metadata
from app.models.transcript import Transcript
from app.search.helpers import Document, encode_params, get_default_index_name


class SearchAdapter(ABC):
    @abstractmethod
    def __init__(
        self, url: str | None = None, api_key: str | None = None, timeout: int = 2
    ):
        pass

    @abstractmethod
    def build_document(
        self,
        id: str | int,
        metadata: Metadata,
        raw_audio_url: str,
        transcript: Transcript,
        geo: GeoResponse | None = None,
    ) -> Document:
        pass

    @abstractmethod
    def build_search_url(self, document: Document, index_name: str) -> str:
        pass

    @abstractmethod
    def index_call(
        self,
        id: int | str,
        metadata: Metadata,
        raw_audio_url: str,
        transcript: Transcript,
        geo: GeoResponse | None = None,
        index_name: str | None = None,
    ) -> str:
        pass

    @abstractmethod
    def create_or_update_index(self, index_name: str):
        pass

    @abstractmethod
    def delete_index(self, index_name: str) -> None:
        pass

    @abstractmethod
    def search(self, index_name: str, query: str, options: dict) -> dict:
        pass

    def make_next_index(self) -> None:
        future_index_name = get_default_index_name(
            datetime.datetime.now() + datetime.timedelta(hours=1)
        )
        if get_default_index_name() != future_index_name:
            self.create_or_update_index(future_index_name)


class MeilisearchAdapter(SearchAdapter):
    def __init__(
        self, url: str | None = None, api_key: str | None = None, timeout: int = 10
    ):
        if not url:
            url = os.getenv("MEILI_URL", "http://meilisearch:7700")
        if not api_key:
            api_key = os.getenv("MEILI_MASTER_KEY")
        self.client = meilisearch.Client(url=url, api_key=api_key, timeout=timeout)

    def build_document(
        self,
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
                {
                    "_geo": geo["geo"],
                    "geo_formatted_address": geo["geo_formatted_address"],
                }
            )

        return doc  # type: ignore

    def build_search_url(self, document: Document, index_name: str) -> str:
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
        self,
        id: int | str,
        metadata: Metadata,
        raw_audio_url: str,
        transcript: Transcript,
        geo: GeoResponse | None = None,
        index_name: str | None = None,
    ) -> str:  # pragma: no cover
        doc = self.build_document(id, metadata, raw_audio_url, transcript, geo)

        logging.debug(f"Sending document to be indexed: {str(doc)}")

        if not index_name:
            call_time = datetime.datetime.fromtimestamp(metadata["start_time"])
            index_name = get_default_index_name(call_time)

        try:
            self.client.index(index_name).add_documents([doc])  # type: ignore
        except MeilisearchApiError as err:
            # Raise a different exception because of https://github.com/celery/celery/issues/6990
            raise MeilisearchError(str(err))

        return self.build_search_url(doc, index_name)

    def create_or_update_index(self, index_name: str) -> Index:  # pragma: no cover
        index = self.client.index(index_name)

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
        while self.client.get_task(task.task_uid).status not in [
            "succeeded",
            "failed",
            "canceled",
        ]:
            sleep(2)

        return index

    def delete_index(self, index_name: str) -> None:
        index = self.client.index(index_name)
        try:
            index.delete()
        except MeilisearchApiError as err:
            if err.code != "index_not_found":
                raise err

    def search(self, index_name: str, query: str, options: dict) -> dict:
        return self.client.index(index_name).search(query, options)


class TypesenseAdapter(SearchAdapter):
    def __init__(
        self, url: str | None = None, api_key: str | None = None, timeout: int = 10
    ):
        if not url:
            url = os.getenv("TYPESENSE_URL", "http://typesense:8108")
        if not api_key:
            api_key = os.getenv("TYPESENSE_API_KEY")

        parsed_url = urlparse(url)
        host = parsed_url.hostname
        port = parsed_url.port or "8108"
        protocol = parsed_url.scheme or "http"

        self.client = typesense.Client(
            {
                "nodes": [{"host": host, "port": port, "protocol": protocol}],
                "api_key": api_key,
                "connection_timeout_seconds": timeout,
            }
        )

    def build_document(
        self,
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

    def build_search_url(self, document: Document, index_name: str) -> str:
        base_url = os.getenv("SEARCH_UI_URL")
        if not base_url:
            return ""
        params = {
            index_name: {
                "sortBy": index_name + "/sort/start_time:desc",
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
        self,
        id: int | str,
        metadata: Metadata,
        raw_audio_url: str,
        transcript: Transcript,
        geo: GeoResponse | None = None,
        index_name: str | None = None,
    ) -> str:  # pragma: no cover
        doc = self.build_document(id, metadata, raw_audio_url, transcript, geo)

        logging.debug(f"Sending document to be indexed: {str(doc)}")

        if not index_name:
            call_time = datetime.datetime.fromtimestamp(metadata["start_time"])
            index_name = get_default_index_name(call_time)

        try:
            self.client.collections[index_name].documents.upsert(doc)  # type: ignore
        except TypesenseClientError as err:
            raise Exception(str(err))

        return self.build_search_url(doc, index_name)

    def create_or_update_index(self, index_name: str) -> Collection:
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
            return self.client.collections[index_name].retrieve()  # type: ignore
        except ObjectNotFound:
            return self.client.collections.create(schema)

    def delete_index(self, index_name: str) -> None:
        try:
            self.client.collections[index_name].delete()  # type: ignore
        except ObjectNotFound:
            pass

    def search(self, index_name: str, query: str, options: dict) -> dict:
        index = self.client.collections[index_name]
        options["q"] = query
        options["query_by"] = "transcript_plaintext"
        return index.documents.search(options)  # type: ignore


def get_default_adapter() -> SearchAdapter:
    if os.getenv("MEILI_URL") and os.getenv("MEILI_API_KEY"):
        from app.search.adapters import MeilisearchAdapter

        return MeilisearchAdapter()
    elif os.getenv("TYPESENSE_URL") and os.getenv("TYPESENSE_API_KEY"):
        from app.search.adapters import TypesenseAdapter

        return TypesenseAdapter()
    else:
        raise ValueError("Invalid search adapter")

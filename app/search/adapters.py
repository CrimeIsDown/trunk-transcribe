import datetime
import json
import logging
import os
from abc import ABC, abstractmethod
from time import sleep
from typing import NotRequired, Set, Tuple, TypedDict
from urllib.parse import urlparse

import typesense
from typesense.collections import Collection
import meilisearch
from meilisearch.errors import MeilisearchApiError, MeilisearchError
from meilisearch.models.document import Document as MeiliDocument
from meilisearch.index import Index
from typesense.exceptions import ObjectNotFound, TypesenseClientError

from app.geocoding.types import GeoResponse
from app.models.metadata import Metadata
from app.models.transcript import Transcript
from app.search.helpers import (
    Document,
    encode_params,
    get_default_index_name,
    get_default_engine,
)


class SearchAdapter(ABC):
    @abstractmethod
    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        timeout: int = 2,
        index_name: str | None = None,
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
    def index_calls(self, documents: list[Document]) -> bool:
        pass

    @abstractmethod
    def upsert_index(
        self,
        index_name: str | None = None,
        update: bool = True,
        enable_embeddings: bool = False,
        dry_run: bool = False,
    ) -> Index | Collection:
        pass

    @abstractmethod
    def set_index(self, index_name: str) -> None:
        pass

    @abstractmethod
    def delete_index(self) -> None:
        pass

    @abstractmethod
    def search(self, query: str, options: dict) -> dict:
        pass

    @abstractmethod
    def get_documents(
        self, pagination: dict, search: dict | None = None
    ) -> Tuple[int, list[Document]]:
        pass

    def make_next_index(self) -> None:
        future_index_name = get_default_index_name(
            datetime.datetime.now() + datetime.timedelta(hours=1)
        )
        if get_default_index_name() != future_index_name:
            self.upsert_index(future_index_name)


class MeilisearchAdapter(SearchAdapter):
    created_indexes: Set[str] = set()

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        timeout: int = 10,
        index_name: str | None = None,
    ):
        if not url:
            url = os.getenv("MEILI_URL", "http://meilisearch:7700")
        if not api_key:
            api_key = os.getenv("MEILI_MASTER_KEY")
        self.client = meilisearch.Client(url=url, api_key=api_key, timeout=timeout)
        if not index_name:
            index_name = get_default_index_name()
        self.set_index(index_name)

    def set_index(self, index_name: str) -> None:
        self.index = self.client.index(index_name)

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

    def parse_document(self, meili_document: MeiliDocument) -> Document:
        return dict(meili_document)["_Document__doc"]

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

        # Since Meilisearch will create a new index with empty settings if we try to index a document into a non-existent index,
        # we need to ensure the index exists before we try to index a document into it
        if index_name not in self.created_indexes:
            self.upsert_index(index_name, update=False)
            self.created_indexes.add(index_name)

        try:
            self.client.index(index_name).add_documents([doc])
        except MeilisearchApiError as err:
            # Raise a different exception because of https://github.com/celery/celery/issues/6990
            raise MeilisearchError(str(err))

        return self.build_search_url(doc, index_name)

    def upsert_index(
        self,
        index_name: str | None = None,
        update: bool = True,
        enable_embeddings: bool = False,
        dry_run: bool = False,
    ) -> Index:  # pragma: no cover
        if index_name:
            index = self.client.index(index_name)
        else:
            index = self.index

        try:
            current_settings = index.get_settings()
            if not update:
                return index
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

        if enable_embeddings:
            desired_settings["embedders"] = {  # type: ignore
                "openai": {
                    "source": "openAi",
                    "apiKey": os.getenv("OPENAI_API_KEY"),
                    "dimensions": 1536,
                    "documentTemplate": "{{doc.transcript_plaintext}}",
                    "model": "text-embedding-3-small",
                }
            }

        for key, value in desired_settings.copy().items():
            if key in current_settings and set(current_settings[key]) == set(value):
                del desired_settings[key]

        # If all the settings match, return the index
        if not desired_settings:
            return index

        logging.info(f"Updating settings: {str(desired_settings)}")
        if dry_run:
            return index

        task = index.update_settings(desired_settings)
        logging.info(f"Waiting for settings update task {task.task_uid} to complete...")
        while self.client.get_task(task.task_uid).status not in [
            "succeeded",
            "failed",
            "canceled",
        ]:
            sleep(2)

        return index

    def delete_index(self) -> None:
        try:
            self.index.delete()
        except MeilisearchApiError as err:
            if err.code != "index_not_found":
                raise err

    def search(self, query: str, options: dict) -> dict:
        return self.index.search(query, options)

    def index_calls(self, documents: list[Document]) -> bool:
        taskinfo = self.index.add_documents(documents)
        task = self.client.get_task(taskinfo.task_uid)
        while task.status not in [
            "succeeded",
            "failed",
            "canceled",
        ]:
            sleep(2)
            task = self.client.get_task(task.uid)
        return task.status == "succeeded"

    def get_documents(
        self, pagination: dict, search: dict | None = None
    ) -> Tuple[int, list[Document]]:
        opts = pagination
        if search:
            opts.update(search)

            if "q" in search:
                query = search["q"]
                # Delete it from opts, not search, so we don't modify the original dict which gets reused
                del opts["q"]

                # Perform the search and process results into the same format as index.get_documents()
                search_results = self.search(query, opts)
                return search_results["estimatedTotalHits"], [
                    self.parse_document(MeiliDocument(hit))
                    for hit in search_results["hits"]
                ]

        results = self.index.get_documents(opts)
        return results.total, [self.parse_document(doc) for doc in results.results]


class TypesenseField(TypedDict):
    name: str
    type: NotRequired[str]
    facet: NotRequired[bool]
    optional: NotRequired[bool]
    embed: NotRequired[dict[str, str | dict[str, str | list[str]] | list[str]]]
    drop: NotRequired[bool]


class TypesenseSchema(TypedDict):
    name: str
    fields: list[TypesenseField]
    default_sorting_field: str


class TypesenseAdapter(SearchAdapter):
    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        timeout: int = 10,
        index_name: str | None = None,
    ):
        if not url:
            url = os.getenv("TYPESENSE_URL", "http://typesense:8108")
        if not api_key:
            api_key = os.getenv("TYPESENSE_API_KEY")

        parsed_url = urlparse(url)
        host = parsed_url.hostname
        protocol = parsed_url.scheme or "http"
        port = parsed_url.port or (443 if protocol == "https" else 80)

        self.client = typesense.Client(
            {
                "nodes": [{"host": host, "port": port, "protocol": protocol}],
                "api_key": api_key,
                "connection_timeout_seconds": timeout,
            }
        )

        if not index_name:
            index_name = get_default_index_name()
        self.set_index(index_name)

    def set_index(self, index_name: str) -> None:
        self.index: Collection = self.client.collections[index_name]

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

    def parse_document(self, typesense_document: dict) -> Document:
        doc = typesense_document
        if "_geo" in doc:
            doc["_geo"] = {"lat": doc["_geo"][0], "lng": doc["_geo"][1]}
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
            self.client.collections[index_name].documents.upsert(doc)
        except ObjectNotFound:
            self.upsert_index(index_name)
            self.client.collections[index_name].documents.upsert(doc)
        except TypesenseClientError as err:
            raise Exception(str(err))

        return self.build_search_url(doc, index_name)

    def upsert_index(
        self,
        index_name: str | None = None,
        update: bool = True,
        enable_embeddings: bool = False,
        dry_run: bool = False,
    ) -> Collection:
        if not index_name:
            index_name = get_default_index_name()
        schema: TypesenseSchema = {
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

        if enable_embeddings:
            schema["fields"].append(
                {
                    "name": "embedding",
                    "type": "float[]",
                    "embed": {
                        "from": [
                            "transcript_plaintext",
                            "talkgroup_hierarchy.lvl2",
                            "geo_formatted_address",
                        ],
                        "model_config": {
                            "model_name": os.getenv(
                                "TYPESENSE_EMBEDDING_MODEL",
                                "openai/text-embedding-3-small",
                            ),
                            "api_key": os.getenv(
                                "TYPESENSE_EMBEDDING_API_KEY",
                                os.getenv("OPENAI_API_KEY", ""),
                            ),
                        },
                    },
                }
            )

        collection: Collection = self.client.collections[index_name]

        try:
            collection_details = collection.retrieve()
        except ObjectNotFound:
            return self.client.collections.create(schema)

        if update:
            current_fields = {
                field["name"]: field for field in collection_details["fields"]
            }
            fields_to_update: list[TypesenseField] = []

            def assert_equal(expected: TypesenseField, actual: TypesenseField) -> bool:
                return (
                    expected["name"] == actual["name"]
                    and expected.get("type") == actual.get("type")
                    and expected.get("facet") == actual.get("facet")
                    and expected.get("optional") == actual.get("optional")
                    and expected.get("embed") == actual.get("embed")
                    and expected.get("drop") == actual.get("drop")
                )

            # Add new or modified fields
            for field in schema["fields"]:
                if field["name"] not in current_fields or not assert_equal(
                    field, current_fields[field["name"]]
                ):
                    if field["name"] in current_fields:
                        # Log the difference between the current and desired field
                        logging.info(
                            f"Updating field {field['name']}: {str(field)} vs {str(current_fields[field['name']])}"
                        )
                        fields_to_update.append({"name": field["name"], "drop": True})
                    fields_to_update.append(field)

            # Drop fields that are not in the desired schema
            schema_field_names = {field["name"] for field in schema["fields"]}
            for field_name in current_fields:
                if field_name not in schema_field_names:
                    fields_to_update.append({"name": field_name, "drop": True})

            if fields_to_update:
                logging.info(f"Updating schema: {str(fields_to_update)}")
                if not dry_run:
                    collection.update({"fields": fields_to_update})
        return collection

    def delete_index(self) -> None:
        try:
            self.index.delete()
        except ObjectNotFound:
            pass

    def index_calls(self, documents: list[Document]) -> bool:
        try:
            self.index.documents.import_(documents)
        except TypesenseClientError as err:
            raise Exception(str(err))
        return True

    def search(self, query: str, options: dict) -> dict:
        options["q"] = query
        options["query_by"] = "transcript_plaintext"
        return self.index.documents.search(options)

    def get_documents(
        self, pagination: dict, search: dict | None = None
    ) -> Tuple[int, list[Document]]:
        opts = pagination
        if not search:
            search = {
                "q": "",
                "query_by": "transcript_plaintext",
                "sort_by": "start_time:desc",
            }

        opts.update(search)

        # Perform the search and process results into the same format as index.get_documents()
        search_results = self.index.documents.search(opts)
        return search_results["found"], [
            self.parse_document(hit["document"]) for hit in search_results["hits"]
        ]


def get_default_adapter(index_name: str | None = None) -> SearchAdapter:
    engine = get_default_engine()
    if engine == "meilisearch":
        return MeilisearchAdapter(index_name=index_name)
    elif engine == "typesense":
        return TypesenseAdapter(index_name=index_name)
    else:
        raise ValueError("Invalid search adapter")

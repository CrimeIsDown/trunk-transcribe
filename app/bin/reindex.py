#!/usr/bin/env python3

import argparse
import csv
import json
import logging
import os
import re
from functools import lru_cache
from typing import Tuple, TypedDict

from dotenv import load_dotenv

# Load the .env file of our choice if specified before the regular .env can load
load_dotenv(os.getenv("ENV"))

from app.geocoding.geocoding import lookup_geo
from app.geocoding.types import GeoResponse
from app.models.metadata import Metadata
from app.models.transcript import Transcript
from app.search import helpers
from app.search.adapters import (
    DatabaseAdapter,
    MeilisearchAdapter,
    SearchAdapter,
    TypesenseAdapter,
)


class SrcListItemUpdate(TypedDict):
    tag: str
    transcript_prompt: str


@lru_cache
def find_src_tag(system: str, src: int) -> SrcListItemUpdate:
    source = str(src)
    for row in UNIT_TAGS.get(system, []):
        pattern = re.compile(row[0])
        if pattern.match(source):
            # Expect row[1] to be like `E$1", "transcript_prompt": "Engine $1 on scene`
            # (this input looks weird, but it's needed to take advantage of trunk-recorder not escaping values in building JSON)
            replacement = row[1].replace("$", "\\")
            result = json.loads(
                '{"tag": "' + re.sub(pattern, replacement, source) + '"}'
            )
            if "transcript_prompt" not in result:
                result["transcript_prompt"] = ""
            return result

    return {"tag": "", "transcript_prompt": ""}


def update_srclist(
    metadata: Metadata, transcript: Transcript
) -> Tuple[Metadata, Transcript]:
    for src in metadata["srcList"]:
        new_tag = find_src_tag(metadata["short_name"], src["src"])
        src["tag"] = new_tag["tag"]
        src["transcript_prompt"] = new_tag["transcript_prompt"]
        transcript.update_src(src)
    return metadata, transcript


def update_document(
    adapter: SearchAdapter, document: helpers.Document, should_lookup_geo: bool = False
) -> helpers.Document:
    metadata: Metadata = json.loads(document["raw_metadata"])
    transcript = Transcript(json.loads(document["raw_transcript"]))

    if UNIT_TAGS.get(metadata["short_name"]):
        metadata, transcript = update_srclist(metadata, transcript)

    if TALKGROUPS.get(metadata["short_name"]):
        try:
            talkgroup = TALKGROUPS[metadata["short_name"]][metadata["talkgroup"]]
            metadata["talkgroup_tag"] = talkgroup["Alpha Tag"].strip()
            metadata["talkgroup_description"] = talkgroup["Description"].strip()
            metadata["talkgroup_group"] = talkgroup["Category"].strip()
            metadata["talkgroup_group_tag"] = talkgroup["Tag"].strip()
        except KeyError:
            logging.warning(
                f"Could not find talkgroup {metadata['talkgroup']} in {metadata['short_name']} CSV file"
            )

    geo: GeoResponse | None
    if (
        "_geo" in document
        and "geo_formatted_address" in document
        and document["geo_formatted_address"]
    ):
        geo = {
            "geo": document["_geo"],  # type: ignore
            "geo_formatted_address": document["geo_formatted_address"],
        }
    elif should_lookup_geo:
        geo = lookup_geo(metadata, transcript)
    else:
        geo = None

    return adapter.build_document(
        document["id"], metadata, document["raw_audio_url"], transcript, geo
    )


# TODO: Move this logic to another script
# def retranscribe(
#     index: Index, documents: list[helpers.Document]
# ) -> Generator[AsyncResult[str]]:
#     for doc in documents:
#         audio_url = doc["raw_audio_url"]
#         metadata: Metadata = json.loads(doc["raw_metadata"])
#         if "digital" in metadata["audio_type"]:
#             from app.radio.digital import build_transcribe_options
#         elif metadata["audio_type"] == "analog":
#             from app.radio.analog import build_transcribe_options

#         yield worker.queue_task(
#             audio_url,
#             metadata,
#             build_transcribe_options(metadata),
#             id=doc["id"],
#             index_name=index.uid,
#         )


def load_csvs(
    unit_tags: list[Tuple[str, str]] | None, talkgroups: list[Tuple[str, str]] | None
) -> Tuple[dict[str, list[list[str]]], dict[str, dict[int, dict[str, str]]]]:
    UNIT_TAGS: dict[str, list[list[str]]] = {}
    if unit_tags:
        for system, file in unit_tags:
            tags: list[list[str]] = []
            with open(file, newline="") as csvfile:
                unit_reader = csv.reader(csvfile, escapechar="\\")
                for row in unit_reader:
                    tags.append(row)
            UNIT_TAGS[system] = tags

    TALKGROUPS: dict[str, dict[int, dict[str, str]]] = {}
    if talkgroups:
        for system, file in talkgroups:
            tgs: dict[int, dict[str, str]] = {}
            with open(file, newline="") as csvfile:
                tg_reader = csv.DictReader(csvfile)
                for row_dict in tg_reader:
                    tgs[int(row_dict["Decimal"])] = dict(row_dict)
            TALKGROUPS[system] = tgs

    return UNIT_TAGS, TALKGROUPS


def get_adapter_class(adapter: str) -> type[SearchAdapter]:
    if adapter == "meilisearch":
        return MeilisearchAdapter
    elif adapter == "typesense":
        return TypesenseAdapter
    elif adapter == "database":
        return DatabaseAdapter
    else:
        raise ValueError(f"Unsupported search engine {adapter}")


def get_source(engine: str, index_name: str) -> SearchAdapter:
    source_class = get_adapter_class(engine)
    if engine == "database":
        # Database adapter doesn't use index names or URLs
        source = source_class()
    elif "@" in index_name:
        parts = index_name.split("@")
        source = source_class(parts[1], index_name=parts[0])
    else:
        source = source_class(index_name=index_name)
    return source


def get_destination(
    engine: str, index_name: str, update_settings: bool = False, dry_run: bool = False
) -> SearchAdapter:
    destination = get_source(engine, index_name)

    if update_settings:
        destination.upsert_index(index_name, dry_run=dry_run)

    return destination


def main(args: argparse.Namespace) -> None:
    source_index_name = args.source_index or args.index
    # For database source, we don't need an index name
    if args.source_engine == "database":
        source_index_name = ""

    source = get_source(args.source_engine, source_index_name)
    destination = get_destination(
        args.destination_engine, args.index, args.update_settings, args.dry_run
    )

    total, _ = source.get_documents({"limit": 1}, args.search)
    logging.info(f"Found {total} total documents")
    limit = args.batch_size if args.source_engine == "meilisearch" else 250
    offset = 0
    total_processed = 0
    updated_documents = []

    action = "re-indexed"

    while offset < total or (args.search and "q" in args.search and total > 0):
        total, docs = source.get_documents(
            {"offset": offset, "limit": limit}, args.search
        )
        if args.search and "q" in args.search and total == 0:
            break
        elif not args.search or "q" not in args.search:
            offset += limit

        completion = min((offset / total) * 100, 100)
        documents = [document for document in docs if eval(args.filter)]

        if len(documents):
            logging.log(
                logging.INFO if args.dry_run else logging.DEBUG,
                "First 5 documents that were matched:\n"
                + json.dumps(
                    [doc for doc in documents[:5]],
                    sort_keys=True,
                    indent=4,
                ),
            )
            docs_to_add = []
            for document in documents:
                if not document:
                    continue
                if args.no_rebuild:
                    docs_to_add.append(document)
                    continue
                docs_to_add.append(
                    update_document(destination, document, args.lookup_geo)
                )
            updated_documents += docs_to_add
            logging.info(f"Added {len(docs_to_add)} documents to be indexed")
            total_processed += len(updated_documents)
            logging.log(
                logging.INFO if args.dry_run else logging.DEBUG,
                f"The updated documents to be {action}:\n"
                + json.dumps(updated_documents[:5], sort_keys=True, indent=4),
            )

            if args.dry_run:
                logging.warning(
                    f"Dry run enabled, exiting. We would have {action} at least {len(documents)} documents"
                )
                break

            if len(updated_documents):
                # Only send the updated docs to be reindexed when we have a big enough batch
                if (
                    len(updated_documents) >= args.batch_size
                    or offset >= total
                    or (args.search and "q" in args.search)
                ):
                    logging.info(
                        f"Waiting for {len(updated_documents)} documents to be {action}"
                    )
                    destination.index_calls(updated_documents)
                    # Reset the list of updated documents
                    updated_documents = []

        logging.info(f"{completion:.2f}% complete ({min(offset, total)}/{total})")

    if not args.dry_run:
        logging.info(
            f"Successfully {action} {total_processed} total matching documents"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Reindex calls.", formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--unit_tags",
        type=str,
        nargs=2,
        metavar=("SHORT_NAME", "UNIT_TAGS_FILE"),
        action="append",
        help="System short_name and the path to the corresponding unitTagsFile CSV",
    )
    parser.add_argument(
        "--talkgroups",
        type=str,
        nargs=2,
        metavar=("SHORT_NAME", "TALKGROUPS_FILE"),
        action="append",
        help="System short_name and the path to the corresponding talkgroupsFile CSV",
    )
    parser.add_argument(
        "--source-engine",
        choices=["meilisearch", "typesense", "database"],
        default=helpers.get_default_engine(),
        help=f"Search engine to use as source, defaults to {helpers.get_default_engine()}. Use 'database' to read directly from the calls table.",
    )
    parser.add_argument(
        "--destination-engine",
        choices=["meilisearch", "typesense"],
        default=helpers.get_default_engine(),
        help=f"Search engine to use, defaults to {helpers.get_default_engine()}",
    )
    parser.add_argument(
        "--index",
        type=str,
        default=helpers.get_default_index_name(),
        help="Search index to use",
    )
    parser.add_argument(
        "--source-index",
        type=str,
        metavar="INDEX",
        help="Search index to read from, will write to the index specified by --index",
    )
    parser.add_argument(
        "--no-rebuild",
        action="store_true",
        help="Use existing documents in the index instead of rebuilding them",
    )
    parser.add_argument(
        "--filter",
        type=str,
        default="True",
        help="Python expression defining whether or not to process a document, by default will process all documents"
        + "\n"
        + 'Examples: `not hasattr(document, "raw_transcript")`, `document.short_name == "system_name" and "123" in document.radios`',
    )
    parser.add_argument(
        "--search",
        type=json.loads,
        help="JSON string representing the search query to perform to find matching documents, instead of fetching all"
        + "\n"
        + 'Examples: `{ "q": "some search" }`, `{"filter": [["talkgroup = 1", "talkgroup = 2"], "radios = 12345"]}`',
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20000,
        help="How many documents to fetch and update in a single request, defaults to 20000",
    )
    # TODO: Move this logic to another script
    # parser.add_argument(
    #     "--retranscribe",
    #     action="store_true",
    #     help="Re-transcribe the matching calls instead of just rebuilding the metadata and reindexing",
    # )
    parser.add_argument(
        "--lookup-geo",
        action="store_true",
        help="Enable geocoding lookup for calls that don't have geo data (useful when sourcing from database)",
    )
    parser.add_argument(
        "--update-settings",
        action="store_true",
        help="Update index settings to match those in search.py",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose mode (debug logging)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the matching documents and associated transformations, without actually doing the reindex",
    )
    args = parser.parse_args()

    logging.basicConfig(
        format="[%(asctime)s] %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    UNIT_TAGS, TALKGROUPS = load_csvs(args.unit_tags, args.talkgroups)

    main(args)

#!/usr/bin/env python3

import argparse
import csv
import json
import logging
import os
import re
from functools import lru_cache
from time import sleep
from typing import Tuple, TypedDict

from celery.result import AsyncResult
from dotenv import load_dotenv
from meilisearch.index import Index
from meilisearch.models.document import Document as MeiliDocument
from meilisearch.models.task import TaskInfo

# Load the .env file of our choice if specified before the regular .env can load
load_dotenv(os.getenv("ENV"))

from app import search
from app.metadata import Metadata
from app.transcript import Transcript
from app.worker import transcribe_task


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


def update_document(document: MeiliDocument) -> search.Document:
    metadata: Metadata = json.loads(document.raw_metadata)
    transcript = Transcript(json.loads(document.raw_transcript))
    if UNIT_TAGS.get(metadata["short_name"]):
        metadata, transcript = update_srclist(metadata, transcript)
    return search.build_document(
        metadata,
        document.raw_audio_url,
        transcript,
        id=document.id,
    )


def reindex(index: Index, documents: list[search.Document]) -> TaskInfo:
    return index.add_documents(documents)  # type: ignore


def retranscribe(index: Index, documents: list[search.Document]) -> list[AsyncResult]:
    return [
        transcribe_task.apply_async(
            queue="retranscribe",
            kwargs={
                "metadata": json.loads(doc["raw_metadata"]),
                "audio_url": doc["raw_audio_url"],
                "id": doc["id"],
                "index_name": index.uid,
            },
        )
        for doc in documents
    ]


def get_documents(
    index: Index, pagination: dict, search: dict | None = None
) -> Tuple[int, list[MeiliDocument]]:
    if search:
        if "q" not in search:
            search["q"] = ""
        query = search["q"]
        # Merge the two dicts via copying
        opts = {**search, **pagination}
        # Delete it from opts, not search, so we don't modify the original dict
        del opts["q"]
        # Perform the search and process results into the same format as index.get_documents()
        results = index.search(query, opts)
        return results["estimatedTotalHits"], [
            MeiliDocument(hit) for hit in results["hits"]
        ]
    else:
        results = index.get_documents(pagination)
        return results.total, results.results


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
        "--index",
        type=str,
        default=search.get_default_index_name(),
        help="Meilisearch index to use",
    )
    parser.add_argument(
        "--copy-from-index",
        type=str,
        metavar="INDEX",
        help="Meilisearch index to read from, will write to the index specified by --index",
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
        + 'Examples: `{ "q": "some search" }`, `{"q": "", "filter": [["talkgroup = 1", "talkgroup = 2"], "radios = 12345"]}`',
    )
    parser.add_argument(
        "--retranscribe",
        action="store_true",
        help="Re-transcribe the matching calls instead of just rebuilding the metadata and reindexing",
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

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    UNIT_TAGS = {}
    if args.unit_tags:
        for system, file in args.unit_tags:
            tags = []
            with open(file, newline="") as csvfile:
                reader = csv.reader(csvfile, escapechar="\\")
                for row in reader:
                    tags.append(row)
            UNIT_TAGS[system] = tags

    client = search.get_client()

    if args.update_settings:
        logging.info(f"Updating settings for index {args.index}")
        search.create_or_update_index(client, args.index, create=False)

    index = search.get_index(args.index)
    source_index = None
    if args.copy_from_index:
        source_index = search.get_index(args.copy_from_index)

    total, _ = get_documents(source_index or index, {"limit": 1}, args.search)
    logging.info(f"Found {total} total documents")
    limit = 2000
    offset = 0
    total_processed = 0
    updated_documents = []

    action = "re-transcribed" if args.retranscribe else "re-indexed"

    while offset < total or (args.search and total > 0):
        total, docs = get_documents(
            source_index or index, {"offset": offset, "limit": limit}, args.search
        )
        if args.search and total == 0:
            break
        elif not args.search:
            offset += limit

        completion = min((offset / total) * 100, 100)
        documents = [document for document in docs if eval(args.filter)]

        if len(documents):
            logging.log(
                logging.INFO if args.dry_run else logging.DEBUG,
                "First 5 documents that were matched:\n"
                + json.dumps(
                    [dict(doc)["_Document__doc"] for doc in documents[:5]],
                    sort_keys=True,
                    indent=4,
                ),
            )
            docs_to_add = list(
                filter(lambda doc: doc is not None, map(update_document, documents))
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
                if args.retranscribe:
                    logging.info(
                        f"Queueing {len(updated_documents)} documents to be {action}"
                    )
                    retranscribe(index, updated_documents)
                else:
                    # Only send the updated docs to be reindexed when we have a big enough batch
                    if len(updated_documents) >= 1000 or offset >= total or args.search:
                        logging.info(
                            f"Waiting for {len(updated_documents)} documents to be {action}"
                        )
                        task = reindex(index, updated_documents)
                        while client.get_task(task.task_uid)["status"] not in [
                            "succeeded",
                            "failed",
                            "canceled",
                        ]:
                            sleep(2)
                        # Reset the list of updated documents
                        updated_documents = []

        logging.info(f"{completion:.2f}% complete ({min(offset, total)}/{total})")

    if not args.dry_run:
        logging.info(
            f"Successfully {action} {total_processed} total matching documents"
        )

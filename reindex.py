#!/usr/bin/env python3

import argparse
import csv
import json
import logging
import os
import re
from functools import lru_cache
from time import sleep
from typing import TypedDict

from dotenv import load_dotenv
from meilisearch.index import Index
from meilisearch.models.document import Document as MeiliDocument
from meilisearch.models.task import TaskInfo

# Load the .env file of our choice if specified before the regular .env can load
load_dotenv(os.getenv("ENV"))

from app import search
from app.metadata import Metadata
from app.worker import retranscribe_task


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
            result = re.sub(pattern, replacement, source)
            return json.loads('{"tag": "' + result + '"}')

    return {"tag": "", "transcript_prompt": ""}


def fix_srclist(metadata: Metadata, transcript: str) -> tuple[Metadata, str]:
    for src in metadata["srcList"]:
        new_tag = find_src_tag(metadata["short_name"], src["src"])
        src["tag"] = new_tag["tag"]
        src["transcript_prompt"] = new_tag["transcript_prompt"]
        transcript = re.sub(
            f'<i data-src="{src["src"]}">(.*?):</i>',
            f'<i data-src="{src["src"]}">{src["tag"] if len(src["tag"]) else src["src"]}:</i>',
            transcript,
        )
    return metadata, transcript


def fix_document(document: MeiliDocument) -> search.Document:
    metadata: Metadata = json.loads(document.raw_metadata)
    if UNIT_TAGS.get(metadata["short_name"]):
        metadata, transcript = fix_srclist(metadata, document.transcript)
    else:
        transcript = document.transcript
    return search.build_document(
        metadata,
        document.raw_audio_url,
        transcript,
        id=document.id,
    )


def reindex(index: Index, documents: list[MeiliDocument]) -> TaskInfo:
    fixed_docs = list(map(fix_document, documents))
    logging.debug(
        "Going to send the following documents to be indexed:\n"
        + json.dumps(fixed_docs, sort_keys=True, indent=4)
    )
    return index.add_documents(fixed_docs)  # type: ignore


def retranscribe(index: Index, documents: list[MeiliDocument]):
    fixed_docs = list(map(fix_document, documents))
    logging.debug(
        "Going to send the following documents to be re-transcribed:\n"
        + json.dumps(fixed_docs, sort_keys=True, indent=4)
    )
    for doc in fixed_docs:
        retranscribe_task.delay(
            metadata=json.loads(doc["raw_metadata"]),
            audio_url=doc["raw_audio_url"],
            id=doc["id"],
            index_name=index.uid,
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Reindex calls.")
    parser.add_argument(
        "--unit_tags",
        type=str,
        nargs=2,
        metavar=("short_name", "unitTagsFile"),
        action="append",
        help="System short_name and the path to the corresponding unitTagsFile CSV",
        required=True,
    )
    parser.add_argument(
        "--index",
        type=str,
        default=search.get_default_index_name(),
        help="Meilisearch index to use",
    )
    parser.add_argument(
        "--condition",
        type=str,
        default="True",
        help="Python expression defining whether or not to process a document",
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
    args = parser.parse_args()

    UNIT_TAGS = {}
    for system, file in args.unit_tags:
        tags = []
        with open(file, newline="") as csvfile:
            reader = csv.reader(csvfile, escapechar="\\")
            for row in reader:
                tags.append(row)
        UNIT_TAGS[system] = tags

    client = search.get_client()

    if args.update_settings:
        search.create_or_update_index(client, args.index, create=False)

    index = search.get_index(args.index)

    total = index.get_documents({"limit": 1}).total
    logging.info(f"Found {total} total documents")
    limit = 2000
    offset = 0

    total_processed = 0

    while offset < total:
        docs = index.get_documents({"offset": offset, "limit": limit})
        offset += limit
        total = docs.total

        queued_tasks = []
        documents = []
        for document in docs.results:
            if eval(args.condition):
                documents.append(document)

        if len(documents):
            if args.retranscribe:
                logging.info(
                    f"Queueing {len(documents)} documents to be re-transcribed"
                )
                retranscribe(index, documents)
            else:
                logging.info(f"Waiting for {len(documents)} documents to be re-indexed")
                task = reindex(index, documents)
                while client.get_task(task.task_uid)["status"] not in [
                    "succeeded",
                    "failed",
                    "canceled",
                ]:
                    sleep(2)

        total_processed += len(documents)
        completion = min((offset / total) * 100, 100)
        logging.info(
            f"Processed {total_processed} matching documents, {completion:.2f}% complete ({offset}/{total})"
        )

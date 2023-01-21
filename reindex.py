#!/usr/bin/env python3

from dotenv import load_dotenv

load_dotenv(".env.vast")

import argparse
import csv
import json
import logging
import re
from functools import lru_cache
from typing import TypedDict

from meilisearch.models.document import Document as MeiliDocument

from app.metadata import Metadata
from app.search import Document, build_document, get_index
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
            f'<i data-src="{src["src"]}">{src["tag"]}:</i>',
            transcript,
        )
    return metadata, transcript


def fix_document(document: MeiliDocument) -> Document:
    metadata: Metadata = json.loads(document.raw_metadata)
    metadata["talkgroup_description"] = metadata["talkgroup_description"].split("|")[0]
    metadata, transcript = fix_srclist(metadata, document.transcript)
    return build_document(
        metadata,
        document.raw_audio_url,
        transcript,
        id=document.id,
    )


def reindex(documents: list[MeiliDocument]):
    fixed_docs = list(map(fix_document, documents))
    logging.debug(
        "Going to send the following documents to be indexed:\n"
        + json.dumps(fixed_docs, sort_keys=True, indent=4)
    )
    get_index().add_documents(fixed_docs)  # type: ignore


def retranscribe(documents: list[MeiliDocument]):
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
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description='Reindex calls.')
    parser.add_argument("--unit_tags", type=str, nargs=2, metavar=("short_name", "unitTagsFile"), action="append", help="System short_name and the path to the corresponding unitTagsFile CSV")
    parser.add_argument("--retranscribe", action="store_true", help="Re-transcribe the matching calls instead of just rebuilding the metadata and reindexing")
    args = parser.parse_args()

    UNIT_TAGS = {}
    for system, file in args.unit_tags:
        tags = []
        with open(file, newline="") as csvfile:
            reader = csv.reader(csvfile, escapechar="\\")
            for row in reader:
                tags.append(row)
        UNIT_TAGS[system] = tags

    total = get_index().get_documents({"limit": 1}).total
    logging.info(f"Found {total} total documents")
    limit = 1000
    offset = -limit

    total_processed = 0

    while offset < total:
        offset += limit
        docs = get_index().get_documents({"offset": offset, "limit": limit})
        total = docs.total

        documents = []
        for document in docs.results:
            # TODO: Find a faster way to filter documents
            if document.short_name in UNIT_TAGS and "data-src" not in document.transcript:
                documents.append(document)

        if len(documents):
            if args.retranscribe:
                retranscribe(documents)
            else:
                reindex(documents)
        total_processed += len(documents)
        completion = min((offset / total) * 100, 100)
        logging.info(
            f"Processed {total_processed} matching documents, {completion:.2f}% complete ({offset}/{total})"
        )

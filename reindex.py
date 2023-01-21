#!/usr/bin/env python3

import json
import logging
import csv
from functools import lru_cache
import re

from meilisearch.models.document import Document

from app.search import get_index, build_document, ID, RAW_METADATA, RAW_AUDIO_URL
from app.worker import retranscribe_task


UNIT_TAGS_FILES = {
    "chi_cfd": "/home/eric/ChicagoScanner/conventional-recorder/config/cfd-radio-ids.csv"
}
UNIT_TAGS = {}

for system, file in UNIT_TAGS_FILES.items():
    tags = []
    with open(file, newline="") as csvfile:
        reader = csv.reader(csvfile, escapechar="\\")
        for row in reader:
            tags.append(row)
    UNIT_TAGS[system] = tags


@lru_cache
def find_src_tag(system: str, src: int) -> dict | None:
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


def fix_srclist(metadata: dict, transcript: str):
    for src in metadata["srcList"]:
        src.update(find_src_tag(metadata["short_name"], src["src"]))
    return metadata


def fix_document(document: Document) -> dict:
    metadata = json.loads(document.raw_metadata)
    metadata["talkgroup_description"] = metadata["talkgroup_description"].split("|")[0]
    metadata = fix_srclist(metadata, document.transcript)
    return build_document(
        metadata,
        getattr(document, RAW_AUDIO_URL),
        document.transcript,
        id=getattr(document, ID),
    )


def reindex(documents: list[Document]):
    fixed_docs = list(map(fix_document, documents))
    logging.debug(
        "Going to send the following documents to be indexed:\n"
        + json.dumps(fixed_docs, sort_keys=True, indent=4)
    )
    get_index().add_documents(fixed_docs)


def retranscribe(documents: list[Document]):
    fixed_docs = list(map(fix_document, documents))
    for doc in fixed_docs:
        retranscribe_task.delay(
            metadata=json.loads(doc[RAW_METADATA]),
            audio_url=doc[RAW_AUDIO_URL],
            id=doc[ID],
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    total = get_index().get_documents({"limit": 1}).total
    logging.info(f"Found {total} total documents")
    limit = 100
    offset = -limit

    total_reindexed = 0

    while offset < total:
        offset += limit
        docs = get_index().get_documents({"offset": offset, "limit": limit})
        total = docs.total

        documents = []
        for document in docs.results:
            if document.audio_type == "digital" and document.short_name == "chi_cfd":
                documents.append(document)

        if len(documents):
            retranscribe(documents)
        total_reindexed += len(documents)
        completion = (offset / total) * 100
        logging.info(
            f"Reindexed {total_reindexed} documents, {completion:.2f}% complete"
        )

#!/usr/bin/env python3

import argparse
import json
import logging
import os
from typing import Tuple

import psycopg
from dotenv import load_dotenv
from meilisearch.index import Index
from meilisearch.models.document import Document as MeiliDocument

# Load the .env file of our choice if specified before the regular .env can load
load_dotenv(os.getenv("ENV"))

from app.search import helpers
from app.search.adapters import MeilisearchAdapter
from app.models import database


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
        results = index.get_documents(pagination)  # type: ignore
        return results.total, results.results  # type: ignore


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Transfer calls from Meilisearch to Postgres.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--index",
        type=str,
        default=helpers.get_default_index_name(),
        help="Meilisearch index to use",
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
        "--verbose",
        action="store_true",
        help="Enable verbose mode (debug logging)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        format="[%(asctime)s] %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    adapter = MeilisearchAdapter()

    index = adapter.client.index(args.index)

    total, _ = get_documents(index, {"limit": 1}, args.search)
    logging.info(f"Found {total} total documents")
    limit = 2000
    offset = 0

    with psycopg.connect(database.SQLALCHEMY_DATABASE_URL) as conn:
        with conn.cursor() as cursor:
            with cursor.copy(
                "COPY calls (raw_metadata, raw_audio_url, raw_transcript, geo) FROM STDIN"
            ) as copy:
                while offset < total or (args.search and total > 0):
                    try:
                        total, docs = get_documents(
                            index, {"offset": offset, "limit": limit}, args.search
                        )
                    except Exception:
                        continue
                    if args.search and total == 0:
                        break
                    elif not args.search:
                        offset += limit

                    completion = min((offset / total) * 100, 100)
                    documents = [document for document in docs if eval(args.filter)]

                    if len(documents):
                        for doc in documents:
                            d = dict(doc)["_Document__doc"]
                            copy.write_row(
                                (
                                    d["raw_metadata"],
                                    d["raw_audio_url"],
                                    d["raw_transcript"],
                                    json.dumps(
                                        {
                                            "_geo": d["_geo"],
                                            "geo_formatted_address": d[
                                                "geo_formatted_address"
                                            ],
                                        }
                                    ),
                                )
                            )

                    logging.info(
                        f"{completion:.2f}% complete ({min(offset, total)}/{total})"
                    )

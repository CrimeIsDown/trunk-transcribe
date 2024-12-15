#!/usr/bin/env python3

import argparse
import json
import logging
import os
from typing import Tuple

from dotenv import load_dotenv
from meilisearch.index import Index
from meilisearch.models.document import Document as MeiliDocument
from typesense.documents import Documents

# Load the .env file of our choice if specified before the regular .env can load
load_dotenv(os.getenv("ENV"))

from app.geocoding.geocoding import GeoResponse
from app.models.metadata import Metadata
from app.models.transcript import Transcript
from app.search import search, search_typesense


def convert_document(document: MeiliDocument) -> search_typesense.Document:
    metadata: Metadata = json.loads(document.raw_metadata)
    transcript = Transcript(json.loads(document.raw_transcript))

    if hasattr(document, "_geo") and hasattr(document, "geo_formatted_address"):
        geo = GeoResponse(
            geo=document._geo,  # type: ignore
            geo_formatted_address=document.geo_formatted_address,
        )
    else:
        geo = None

    return search_typesense.build_document(
        document.id, metadata, document.raw_audio_url, transcript, geo
    )


def _import(collection: Documents, documents: list[search_typesense.Document]):
    return collection.import_(documents, {"action": "upsert"})


def get_documents(index: Index, pagination: dict) -> Tuple[int, list[MeiliDocument]]:
    opts = pagination

    results = index.get_documents(opts)
    return results.total, results.results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import calls from Meilisearch into Typesense.", formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20000,
        help="How many documents to fetch and update in a single request, defaults to 20000",
    )
    parser.add_argument(
        "--index",
        type=str,
        default="calls",
        help="The index to reindex, defaults to 'calls'",
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

    meili_client = search.get_client()
    typesense_client = search_typesense.get_client(timeout=86400)

    index = meili_client.index(args.index)

    # Create collection in typesense
    search_typesense.create_or_update_index(typesense_client, args.index)
    collection_docs = typesense_client.collections[args.index].documents  # type: ignore

    total, _ = get_documents(index, {"limit": 1})
    logging.info(f"Found {total} total documents")
    limit = args.batch_size
    offset = 0
    total_processed = 0
    updated_documents = []

    while offset < total:
        total, documents = get_documents(index, {"offset": offset, "limit": limit})
        offset += limit

        completion = min((offset / total) * 100, 100)

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
                filter(
                    lambda doc: doc is not None,
                    map(lambda d: convert_document(d), documents),
                )
            )
            updated_documents += docs_to_add
            logging.info(f"Added {len(docs_to_add)} documents to be indexed")
            total_processed += len(updated_documents)
            logging.log(
                logging.INFO if args.dry_run else logging.DEBUG,
                f"The documents to be imported:\n"
                + json.dumps(updated_documents[:5], sort_keys=True, indent=4),
            )

            if args.dry_run:
                logging.warning(
                    f"Dry run enabled, exiting. We would have imported at least {len(documents)} documents"
                )
                break

            if len(updated_documents):
                # Only send the updated docs to be reindexed when we have a big enough batch
                if (
                    len(updated_documents) >= limit
                    or offset >= total
                ):
                    logging.info(
                        f"Waiting for {len(updated_documents)} documents to be imported"
                    )
                    _import(collection_docs, updated_documents)
                    # Reset the list of updated documents
                    updated_documents = []

        logging.info(f"{completion:.2f}% complete ({min(offset, total)}/{total})")

    if not args.dry_run:
        logging.info(
            f"Successfully imported {total_processed} total matching documents"
        )

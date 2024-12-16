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
from app.search import helpers, adapters


def convert_document(document: MeiliDocument) -> helpers.Document:
    metadata: Metadata = json.loads(document.raw_metadata)
    transcript = Transcript(json.loads(document.raw_transcript))

    if hasattr(document, "_geo") and hasattr(document, "geo_formatted_address"):
        geo = GeoResponse(
            geo=document._geo,  # type: ignore
            geo_formatted_address=document.geo_formatted_address,
        )
    else:
        geo = None

    return typesense_adapter.build_document(
        document.id, metadata, document.raw_audio_url, transcript, geo
    )


def _import(collection: Documents, documents: list[helpers.Document]):
    return collection.import_(
        documents, {"action": "upsert", "batch_size": len(documents)}
    )


def get_documents(index: Index, pagination: dict) -> Tuple[int, list[MeiliDocument]]:
    opts = pagination

    results = index.get_documents(opts)
    return results.total, results.results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import calls from Meilisearch into Typesense.",
        formatter_class=argparse.RawTextHelpFormatter,
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
        default=helpers.get_default_index_name(),
        help=f"The index to reindex, defaults to '{helpers.get_default_index_name()}'",
    )
    parser.add_argument(
        "--all-indices",
        action="store_true",
        help="Reindex all indices",
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

    meili_adapter = adapters.MeilisearchAdapter(timeout=60 * 60)
    typesense_adapter = adapters.TypesenseAdapter(timeout=60 * 60)

    indicies = [args.index]

    if args.all_indices:
        indicies = [
            index.uid for index in meili_adapter.client.get_indexes()["results"]
        ]

    # Sort indicies to ensure we always process them in the same order
    indicies.sort()

    for index in indicies:
        logging.info(f"Reindexing index: {index}")

        meili_index = meili_adapter.client.index(index)

        # Create collection in typesense
        typesense_adapter.create_or_update_index(index)
        collection_docs = typesense_adapter.client.collections[index].documents  # type: ignore

        total, _ = get_documents(meili_index, {"limit": 1})
        logging.info(f"Found {total} total documents")
        limit = args.batch_size
        offset = 0
        total_processed = 0
        updated_documents = []

        while offset < total:
            total, documents = get_documents(
                meili_index, {"offset": offset, "limit": limit}
            )
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
                    "The documents to be imported:\n"
                    + json.dumps(updated_documents[:5], sort_keys=True, indent=4),
                )

                if args.dry_run:
                    logging.warning(
                        f"Dry run enabled, exiting. We would have imported at least {len(documents)} documents"
                    )
                    break

                if len(updated_documents):
                    # Only send the updated docs to be reindexed when we have a big enough batch
                    if len(updated_documents) >= limit or offset >= total:
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

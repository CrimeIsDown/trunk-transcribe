#!/usr/bin/env python3

import argparse
import json
import logging
import os
from typing import Iterator

from dotenv import load_dotenv
from typesense.collections import Collection

# Load the .env file of our choice if specified before the regular .env can load
load_dotenv(os.getenv("ENV"))

from app.geocoding.types import GeoResponse
from app.models.metadata import Metadata
from app.models.transcript import Transcript
from app.search import helpers, adapters


def convert_document(document: dict) -> helpers.Document:
    """Convert a Typesense document to a Meilisearch document format."""
    metadata: Metadata = json.loads(document["raw_metadata"])
    transcript = Transcript(json.loads(document["raw_transcript"]))

    if "_geo" in document and "geo_formatted_address" in document:
        geo = GeoResponse(
            geo=document["_geo"],
            geo_formatted_address=document["geo_formatted_address"],
        )
    else:
        geo = None

    return meili_adapter.build_document(
        document["id"], metadata, document["raw_audio_url"], transcript, geo
    )


def export_documents(collection: Collection) -> Iterator[dict]:
    """Export all documents from a Typesense collection using the export endpoint."""
    try:
        # Use Typesense export endpoint which returns JSONL format
        response = collection.documents.export()

        # Split the response by newlines and parse each JSON object
        for line in response.split('\n'):
            if line.strip():  # Skip empty lines
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as e:
                    logging.warning(f"Failed to parse JSON line: {line[:100]}... Error: {e}")
                    continue
    except Exception as e:
        logging.error(f"Failed to export documents: {e}")
        raise


def import_documents(documents: list[helpers.Document]):
    """Import documents into Meilisearch."""
    if not documents:
        return

    task = meili_adapter.index.add_documents(documents)
    logging.debug(f"Meilisearch import task: {task}")
    return task


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate calls from Typesense to Meilisearch using Typesense export endpoint.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="How many documents to import in a single batch, defaults to 1000",
    )
    parser.add_argument(
        "--index",
        type=str,
        default=helpers.get_default_index_name(),
        help=f"The index to migrate, defaults to '{helpers.get_default_index_name()}'",
    )
    parser.add_argument(
        "--all-indices",
        action="store_true",
        help="Migrate all indices",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose mode (debug logging)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the matching documents and associated transformations, without actually doing the migration",
    )
    args = parser.parse_args()

    logging.basicConfig(
        format="[%(asctime)s] %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    typesense_adapter = adapters.TypesenseAdapter(timeout=60 * 60)
    meili_adapter = adapters.MeilisearchAdapter(timeout=60 * 60)

    indices = [args.index]

    if args.all_indices:
        try:
            # Get all collections from Typesense
            collections = typesense_adapter.client.collections.retrieve()
            indices = [collection["name"] for collection in collections]
        except Exception as e:
            logging.error(f"Failed to retrieve Typesense collections: {e}")
            exit(1)

    # Sort indices to ensure we always process them in the same order
    indices.sort()

    for index in indices:
        logging.info(f"Migrating index: {index}")

        try:
            typesense_collection = typesense_adapter.client.collections[index]
        except Exception as e:
            logging.error(f"Failed to access Typesense collection '{index}': {e}")
            continue

        # Create/update index in Meilisearch
        meili_adapter.set_index(index)
        meili_adapter.upsert_index(index)

        total_processed = 0
        batch_documents = []

        try:
            # Export all documents from Typesense
            logging.info("Starting export from Typesense...")

            for i, document in enumerate(export_documents(typesense_collection)):
                if args.dry_run and i < 5:
                    logging.info(f"Sample document {i + 1}:\n" + json.dumps(document, sort_keys=True, indent=2))

                try:
                    converted_doc = convert_document(document)
                    batch_documents.append(converted_doc)

                    # Process in batches
                    if len(batch_documents) >= args.batch_size:
                        if args.dry_run:
                            logging.info(f"Would import batch of {len(batch_documents)} documents")
                        else:
                            logging.debug(f"Importing batch of {len(batch_documents)} documents")
                            import_documents(batch_documents)

                        total_processed += len(batch_documents)
                        batch_documents = []

                        if total_processed % 10000 == 0:
                            logging.info(f"Processed {total_processed} documents so far...")

                except Exception as e:
                    logging.warning(f"Failed to convert document {document.get('id', 'unknown')}: {e}")
                    continue

            # Process remaining documents in the final batch
            if batch_documents:
                if args.dry_run:
                    logging.info(f"Would import final batch of {len(batch_documents)} documents")
                else:
                    logging.debug(f"Importing final batch of {len(batch_documents)} documents")
                    import_documents(batch_documents)

                total_processed += len(batch_documents)

        except Exception as e:
            logging.error(f"Failed to export/import documents for index '{index}': {e}")
            continue

        if args.dry_run:
            logging.info(f"Dry run complete for index '{index}'. Would have migrated {total_processed} documents.")
        else:
            logging.info(f"Successfully migrated {total_processed} documents from index '{index}'")

    if not args.dry_run:
        logging.info("Migration completed successfully!")
    else:
        logging.info("Dry run completed successfully!")

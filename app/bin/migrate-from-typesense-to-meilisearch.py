#!/usr/bin/env python3

import argparse
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
import jsonlines

# Load the .env file of our choice if specified before the regular .env can load
load_dotenv(os.getenv("ENV"))

from app.geocoding.types import Geo, GeoResponse
from app.models.metadata import Metadata
from app.models.transcript import Transcript
from app.search import helpers, adapters


def convert_document(document: dict) -> helpers.Document:
    """Convert a Typesense document to a Meilisearch document format."""
    metadata: Metadata = json.loads(document["raw_metadata"])
    transcript = Transcript(json.loads(document["raw_transcript"]))

    if "_geo" in document and "geo_formatted_address" in document:
        coords = Geo(lat=document["_geo"][0], lng=document["_geo"][1])
        geo = GeoResponse(
            geo=coords,
            geo_formatted_address=document["geo_formatted_address"],
        )
    else:
        geo = None

    return meili_adapter.build_document(
        document["id"], metadata, document["raw_audio_url"], transcript, geo
    )


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
        batch_documents: list[helpers.Document] = []

        try:
            # Export all documents from Typesense
            logging.info("Starting export from Typesense...")
            export_filename = f"{index}.jsonl"

            if not Path(export_filename).exists():
                with open(export_filename, "w") as export_file:
                    export_file.write(typesense_collection.documents.export())

            with jsonlines.open(export_filename) as reader:
                i = 0
                for document in reader.iter(type=dict):
                    if args.dry_run and i < 5:
                        logging.info(
                            f"Sample document {i + 1}:\n"
                            + json.dumps(document, sort_keys=True, indent=2)
                        )
                    i += 1

                    try:
                        converted_doc = convert_document(document)
                        batch_documents.append(converted_doc)

                        # Process in batches
                        if len(batch_documents) >= args.batch_size:
                            if args.dry_run:
                                logging.info(
                                    f"Would import batch of {len(batch_documents)} documents"
                                )
                            else:
                                logging.info(
                                    f"Importing batch of {len(batch_documents)} documents"
                                )
                                meili_adapter.index_calls(batch_documents)

                            total_processed += len(batch_documents)
                            batch_documents = []

                            if total_processed % 10000 == 0:
                                logging.info(
                                    f"Processed {total_processed} documents so far..."
                                )

                    except Exception as e:
                        logging.warning(
                            f"Failed to convert document {document.get('id', 'unknown')}: {e}"
                        )
                        continue

            # Process remaining documents in the final batch
            if batch_documents:
                if args.dry_run:
                    logging.info(
                        f"Would import final batch of {len(batch_documents)} documents"
                    )
                else:
                    logging.debug(
                        f"Importing final batch of {len(batch_documents)} documents"
                    )
                    meili_adapter.index_calls(batch_documents)

                total_processed += len(batch_documents)

        except Exception as e:
            logging.error(f"Failed to export/import documents for index '{index}': {e}")
            continue

        if args.dry_run:
            logging.info(
                f"Dry run complete for index '{index}'. Would have migrated {total_processed} documents."
            )
        else:
            logging.info(
                f"Successfully migrated {total_processed} documents from index '{index}'"
            )

    if not args.dry_run:
        logging.info("Migration completed successfully!")
    else:
        logging.info("Dry run completed successfully!")

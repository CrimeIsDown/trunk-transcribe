#!/usr/bin/env python3

import argparse
import logging
import os
import time

from dotenv import load_dotenv

# Load the .env file of our choice if specified before the regular .env can load
load_dotenv(os.getenv("ENV"))

from app.models.models import refresh_talkgroup_search_materialized_view


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh the talkgroup search materialized view.",
    )
    parser.add_argument(
        "--no-concurrently",
        action="store_true",
        help="Refresh without CONCURRENTLY. This can be faster but takes a stronger lock.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        format="[%(asctime)s] %(message)s",
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    concurrently = not args.no_concurrently
    started = time.perf_counter()
    logging.info(
        "Refreshing talkgroup search materialized view%s",
        " concurrently" if concurrently else "",
    )
    refresh_talkgroup_search_materialized_view(concurrently=concurrently)
    elapsed = time.perf_counter() - started
    logging.info("Talkgroup search materialized view refreshed in %.2fs", elapsed)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3

import argparse
import json
import logging
import os
import tarfile
import tempfile
import uuid
from io import BytesIO
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv
from sqlmodel import Session, select
from tqdm import tqdm

# Load the .env file of our choice if specified before the regular .env can load
load_dotenv(os.getenv("ENV"))

from app.models import database
from app.models.models import Call
from app.utils.conversion import convert_to_wav


def download_and_convert_audio(url: str, timeout: int = 30) -> Optional[bytes]:
    """Download audio file from URL, convert to WAV, and return bytes."""
    temp_downloaded = None
    temp_converted = None

    try:
        # Download the original audio file
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()

        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".audio") as temp_file:
            temp_file.write(response.content)
            temp_downloaded = temp_file.name

        # Convert to WAV using existing utility
        temp_converted = convert_to_wav(temp_downloaded)

        # Read the converted WAV file
        with open(temp_converted, "rb") as wav_file:
            wav_bytes = wav_file.read()

        return wav_bytes

    except Exception as e:
        logging.warning(f"Failed to download/convert audio from {url}: {e}")
        return None

    finally:
        # Clean up temporary files
        if temp_downloaded and os.path.exists(temp_downloaded):
            os.unlink(temp_downloaded)
        if temp_converted and os.path.exists(temp_converted):
            os.unlink(temp_converted)


def generate_webdataset(
    output_dir: str,
    limit: Optional[int] = None,
    max_tar_size_mb: int = 100,
    filter_min_transcript_length: int = 10,
    timeout: int = 30,
) -> None:
    """
    Generate a Hugging Face WebDataset with TAR archives containing WAV audio and JSON metadata.
    All audio files are converted to 16kHz mono WAV format for consistency.

    Args:
        output_dir: Directory to save the TAR files
        limit: Maximum number of records to include (None for all)
        max_tar_size_mb: Maximum size of each TAR file in MB
        filter_min_transcript_length: Minimum transcript length to include
        timeout: Timeout for audio download requests
    """

    logging.info("Connecting to database...")
    engine = database.engine

    # Ensure output directory exists
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    with Session(engine) as session:
        # Query for calls with both audio URLs and transcripts
        query = select(Call).where(
            Call.raw_audio_url.is_not(None),
            Call.transcript_plaintext.is_not(None),
            Call.transcript_plaintext != "",
        )

        if filter_min_transcript_length > 0:
            logging.info(
                f"Filtering transcripts with minimum length of {filter_min_transcript_length} characters..."
            )

        if limit:
            query = query.limit(limit)
            logging.info(f"Limiting results to {limit} records")

        calls = session.exec(query).all()

        if not calls:
            logging.error("No calls found with both audio URLs and transcripts")
            return

        logging.info(f"Found {len(calls)} calls with audio and transcripts")

        # WebDataset generation
        tar_index = 0
        current_tar = None
        current_tar_size = 0
        max_tar_size_bytes = max_tar_size_mb * 1024 * 1024

        failed_downloads = 0
        processed_count = 0

        def create_new_tar():
            nonlocal current_tar, tar_index, current_tar_size

            if current_tar:
                current_tar.close()

            tar_filename = output_path / f"train-{tar_index:05d}.tar"
            current_tar = tarfile.open(tar_filename, "w")
            current_tar_size = 0
            tar_index += 1
            logging.info(f"Created new TAR archive: {tar_filename}")

        # Create first TAR file
        create_new_tar()

        try:
            for call in tqdm(calls, desc="Processing calls"):
                # Filter by transcript length if specified
                if (
                    call.transcript_plaintext
                    and len(call.transcript_plaintext.strip())
                    < filter_min_transcript_length
                ):
                    continue

                # Download and convert audio file to WAV
                audio_bytes = download_and_convert_audio(
                    call.raw_audio_url, timeout=timeout
                )
                if audio_bytes is None:
                    failed_downloads += 1
                    continue

                # Generate unique prefix for this example
                prefix = str(uuid.uuid4()).replace("-", "")

                # All audio files are converted to WAV
                audio_ext = ".wav"

                # Create metadata JSON
                metadata = {
                    "transcript": call.transcript_plaintext.strip(),
                    "call_id": call.id,
                    "start_time": call.start_time.isoformat()
                    if call.start_time
                    else None,
                    "audio_url": call.raw_audio_url,
                }

                # Add raw metadata if available
                if call.raw_metadata:
                    metadata["raw_metadata"] = call.raw_metadata

                # Add geo data if available
                if call.geo:
                    metadata["geo"] = call.geo

                metadata_json = json.dumps(metadata, ensure_ascii=False, indent=2)

                # Calculate sizes
                audio_size = len(audio_bytes)
                metadata_size = len(metadata_json.encode("utf-8"))
                total_size = audio_size + metadata_size

                # Check if we need a new TAR file
                if (
                    current_tar_size + total_size > max_tar_size_bytes
                    and processed_count > 0
                ):
                    create_new_tar()

                # Add audio file to TAR
                audio_info = tarfile.TarInfo(name=f"{prefix}{audio_ext}")
                audio_info.size = audio_size
                current_tar.addfile(audio_info, fileobj=BytesIO(audio_bytes))

                # Add metadata JSON to TAR
                json_info = tarfile.TarInfo(name=f"{prefix}.json")
                json_info.size = metadata_size
                current_tar.addfile(
                    json_info, fileobj=BytesIO(metadata_json.encode("utf-8"))
                )

                current_tar_size += total_size
                processed_count += 1

        finally:
            if current_tar:
                current_tar.close()

        if failed_downloads > 0:
            logging.warning(f"Failed to download {failed_downloads} audio files")

        logging.info(f"Generated WebDataset with {processed_count} examples")
        logging.info(f"Created {tar_index} TAR archive(s) in {output_dir}")
        logging.info(f"Average examples per TAR: {processed_count / tar_index:.1f}")

        # List created files
        tar_files = list(output_path.glob("*.tar"))
        total_size_mb = sum(f.stat().st_size for f in tar_files) / (1024 * 1024)
        logging.info(f"Total dataset size: {total_size_mb:.1f} MB")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate a Hugging Face WebDataset from call transcripts and audio files.\nAll audio files are converted to 16kHz mono WAV format.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        required=True,
        help="Output directory for the TAR files (e.g., 'dataset_webdataset/')",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of records to include (default: all records)",
    )
    parser.add_argument(
        "--max-tar-size",
        type=int,
        default=100,
        help="Maximum size of each TAR file in MB (default: 100)",
    )
    parser.add_argument(
        "--min-transcript-length",
        type=int,
        default=10,
        help="Minimum transcript length in characters (default: 10)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout for audio download requests in seconds (default: 30)",
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

    try:
        generate_webdataset(
            output_dir=args.output_dir,
            limit=args.limit,
            max_tar_size_mb=args.max_tar_size,
            filter_min_transcript_length=args.min_transcript_length,
            timeout=args.timeout,
        )
    except KeyboardInterrupt:
        logging.info("Process interrupted by user")
    except Exception as e:
        logging.error(f"Error generating WebDataset: {e}")
        raise

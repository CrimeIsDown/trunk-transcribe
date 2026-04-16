#!/usr/bin/env python3

import argparse
import os

from dotenv import load_dotenv

from app.whisper.base import TranscribeOptions
from app.whisper.transcribe import cleanup_transcript
from app.core.transcription_profiles import (
    build_pool_profile,
    build_vendor_profile,
)

load_dotenv()

from app.whisper.config import get_transcript_cleanup_config, get_whisper_config
from app.whisper.task import TranscriptionTask

parser = argparse.ArgumentParser(description="Audio Transcription CLI")
parser.add_argument("audio_file", help="Path to the audio file")
parser.add_argument(
    "--profile",
    default=os.getenv("TRANSCRIPTION_PROFILE"),
    help="Structured transcription profile string",
)
parser.add_argument(
    "--provider",
    default=os.getenv("ASR_PROVIDER") or os.getenv("WHISPER_IMPLEMENTATION", "speaches"),
    help="ASR provider to use when --profile is not set",
)
parser.add_argument(
    "--model",
    default=os.getenv("ASR_MODEL")
    or os.getenv("WHISPER_MODEL", "Systran/faster-distil-whisper-small.en"),
    help="ASR model to use when --profile is not set",
)
parser.add_argument("--prompt", help="Prompt to pass to the ASR backend")
parser.add_argument(
    "--cleanup", action="store_true", help="Perform cleanup on the transcript"
)
parser.add_argument(
    "--vad_filter", action="store_true", help="Apply VAD filter to audio"
)


def main():
    args = parser.parse_args()

    profile = args.profile
    if not profile:
        if args.provider in {"openai", "deepinfra"}:
            profile = build_vendor_profile(args.provider, args.model)
        else:
            profile = build_pool_profile(
                platform="local",
                family=os.getenv("TRANSCRIPTION_BACKEND", "whisper"),
                variant=os.getenv("ASR_VARIANT", "cli"),
                provider=args.provider,
                model=args.model,
            )

    model = TranscriptionTask().model(profile)

    options: TranscribeOptions = {
        "cleanup": args.cleanup,
        "vad_filter": args.vad_filter,
        "initial_prompt": args.prompt,
        "decode_options": get_whisper_config(),
        "cleanup_config": get_transcript_cleanup_config(),
    }
    result = model.transcribe(args.audio_file, options)

    print(
        cleanup_transcript(result, options["cleanup_config"])
        if args.cleanup
        else result
    )


if __name__ == "__main__":
    main()

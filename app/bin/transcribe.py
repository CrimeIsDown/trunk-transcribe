#!/usr/bin/env python3

import argparse

from dotenv import load_dotenv

from app.whisper.base import TranscribeOptions
from app.whisper.transcribe import cleanup_transcript

load_dotenv()

from app.whisper.config import get_transcript_cleanup_config, get_whisper_config
from app.whisper.task import WhisperTask

parser = argparse.ArgumentParser(description="Audio Transcription CLI")
parser.add_argument("audio_file", help="Path to the audio file")
parser.add_argument(
    "--implementation", default="whisper", help="Specify the implementation to use"
)
parser.add_argument("--model", default="small.en", help="Whisper model to use")
parser.add_argument("--prompt", help="Prompt to pass to Whisper")
parser.add_argument(
    "--cleanup", action="store_true", help="Perform cleanup on the transcript"
)
parser.add_argument(
    "--vad_filter", action="store_true", help="Apply VAD filter to audio"
)


def main():
    args = parser.parse_args()

    model = WhisperTask().model(f"{args.implementation}:{args.model}")

    options: TranscribeOptions = {
        "cleanup": args.cleanup,
        "vad_filter": args.vad_filter,
        "initial_prompt": args.prompt,
        "decode_options": get_whisper_config(),
        "cleanup_config": get_transcript_cleanup_config(),
    }
    result = model.transcribe(args.audio_file, options)

    print(cleanup_transcript(result, options["cleanup_config"]) if args.cleanup else result)


if __name__ == "__main__":
    main()

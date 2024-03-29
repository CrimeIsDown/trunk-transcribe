#!/usr/bin/env python3

import sys
from os import path

sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

import argparse

from dotenv import load_dotenv

load_dotenv()

from app import whisper

parser = argparse.ArgumentParser(description="Audio Transcription CLI")
parser.add_argument("audio_file", help="Path to the audio file")
parser.add_argument(
    "--implementation", default="whisper", help="Specify the implementation to use"
)
parser.add_argument("--model", default="small.en", help="Whisper model to use")
parser.add_argument("--prompt", help="Prompt to pass to Whisper")


def main():
    args = parser.parse_args()

    model = whisper.WhisperTask().model(f"{args.implementation}:{args.model}")

    result = model.transcribe(args.audio_file, initial_prompt=args.prompt)

    print(result)


if __name__ == "__main__":
    main()

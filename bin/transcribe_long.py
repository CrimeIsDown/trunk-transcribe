#!/usr/bin/env python3

import argparse
import os
from pathlib import Path
from typing import Optional

import torch
import whisper_s2t
from whisper_s2t.backends.ctranslate2.model import BEST_ASR_CONFIG


def initialize_model(model_name: str = "large-v2", backend: str = "CTranslate2"):
    torch_device = os.getenv(
        "TORCH_DEVICE", "cuda:0" if torch.cuda.is_available() else "cpu"
    )
    device = torch_device.split(":")[0]
    device_index = torch_device.split(":")[1] if ":" in torch_device else "0"
    device_index = (
        [int(i) for i in device_index.split(",")]
        if "," in device_index
        else int(device_index)
    )
    compute_type = os.getenv(
        "TORCH_DTYPE",
        "int8" if "cpu" in os.getenv("TORCH_DEVICE", "") else "float16",
    )
    model_kwargs = {
        "asr_options": BEST_ASR_CONFIG,
        "device": device,
        "device_index": device_index,
        "compute_type": compute_type,
    }
    model_kwargs["asr_options"]["without_timestamps"] = False
    model_kwargs["asr_options"]["word_timestamps"] = True
    return whisper_s2t.load_model(
        model_identifier=model_name, backend=backend, **model_kwargs
    )


def transcribe(
    files: list[str], initial_prompts: Optional[list[str]] = None, format: str = "vtt"
):
    model = initialize_model()

    lang_codes = ["en"]
    tasks = ["transcribe"]

    out = model.transcribe_with_vad(
        files,
        lang_codes=lang_codes,  # pass lang_codes for each file
        tasks=tasks,  # pass transcribe/translate
        initial_prompts=initial_prompts,  # to do prompting (currently only supported for CTranslate2 backend)
        batch_size=12,
    )

    op_files = []

    for file in files:
        inpath = Path(file)
        op_files.append(inpath.with_suffix(f".{format}"))

    whisper_s2t.write_outputs(out, format=format, op_files=op_files)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transcribe audio files")
    parser.add_argument(
        "files", metavar="files", type=str, nargs="+", help="audio files to transcribe"
    )
    parser.add_argument(
        "--initial-prompts",
        dest="initial_prompts",
        type=str,
        nargs="+",
        help="initial prompts for each file",
    )
    parser.add_argument(
        "--format",
        dest="format",
        type=str,
        default="vtt",
        help="output format (default: vtt)",
    )
    args = parser.parse_args()

    transcribe(args.files, initial_prompts=args.initial_prompts, format=args.format)

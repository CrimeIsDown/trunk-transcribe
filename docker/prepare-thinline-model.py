#!/usr/bin/env python3
"""Prepare a ThinLine R05 checkpoint for the local Speaches worker."""

import argparse
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import urlopen
from zipfile import ZipFile

VARIANTS = {
    "large-v3": "model-full.zip",
    "large-v3-turbo": "model-turbo-full.zip",
    "medium": "model-medium-full.zip",
    "small": "model-small-full.zip",
    "tiny": "model-tiny-full.zip",
}


def prepare(variant: str, cache: Path, archive: Path | None) -> Path:
    from ctranslate2.converters import TransformersConverter
    from transformers import WhisperTokenizerFast

    model = f"whisper-r05-{variant}"
    repo = cache / f"models--thinline--{model}"
    snapshot = repo / "snapshots" / "r05"
    if (snapshot / "model.bin").is_file():
        return snapshot

    cache.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=cache) as temp_dir:
        staging = Path(temp_dir)
        if archive is None:
            url = f"https://transcripts.thinlineds.com/api/public/{VARIANTS[variant]}"
            print(f"Downloading {url}", flush=True)
            archive = staging / "model.zip"
            with urlopen(url, timeout=60) as download, archive.open("wb") as output:
                shutil.copyfileobj(download, output)

        source = staging / "source"
        source.mkdir()
        size_suffix = VARIANTS[variant].removeprefix("model").removesuffix("-full.zip")
        model_directory = f"thinline-whisper{size_suffix}-r05-full"
        with ZipFile(archive) as bundle:
            for member in bundle.infolist():
                # Publisher ZIPs put the model files inside a single top-level directory.
                path = Path(member.filename)
                if not member.is_dir() and path.parent == Path(model_directory):
                    with (
                        bundle.open(member) as contents,
                        (source / path.name).open("wb") as output,
                    ):
                        shutil.copyfileobj(contents, output)

        if not (source / "model.safetensors").is_file():
            raise ValueError(
                f"Archive does not contain the merged ThinLine R05 {variant} model"
            )

        # Transformers 5 writes a list where Transformers 4 expects a mapping.
        tokenizer_config = source / "tokenizer_config.json"
        config = json.loads(tokenizer_config.read_text())
        if isinstance(config.get("extra_special_tokens"), list):
            config["additional_special_tokens"] = config.pop("extra_special_tokens")
            tokenizer_config.write_text(json.dumps(config))
        if not (source / "tokenizer.json").exists():
            WhisperTokenizerFast.from_pretrained(source).save_pretrained(source)
        preprocessor = source / "preprocessor_config.json"
        if not preprocessor.exists():
            processor = json.loads((source / "processor_config.json").read_text())
            preprocessor.write_text(json.dumps(processor["feature_extractor"]))

        staged_repo = staging / repo.name
        staged_snapshot = staged_repo / "snapshots" / snapshot.name
        staged_snapshot.parent.mkdir(parents=True)
        print(f"Converting {model} to CTranslate2 float16", flush=True)
        TransformersConverter(
            str(source),
            copy_files=["tokenizer.json", "preprocessor_config.json"],
            load_as_float16=True,
        ).convert(str(staged_snapshot), quantization="float16")
        (staged_snapshot / "README.md").write_text(
            "---\nlibrary_name: ctranslate2\npipeline_tag: automatic-speech-recognition\n"
            "---\n"
            f"# ThinLine {model}\n\nSource: https://transcripts.thinlineds.com/\n"
        )
        (staged_repo / "refs").mkdir()
        (staged_repo / "refs" / "main").write_text(snapshot.name)
        # Publish the cache entry only after conversion succeeds.
        try:
            staged_repo.rename(repo)
        except OSError:
            if not (snapshot / "model.bin").is_file():
                raise
    return snapshot


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("variant", choices=VARIANTS)
    parser.add_argument("--cache", type=Path, default=Path("scratch/thinline-models"))
    parser.add_argument(
        "--archive", type=Path, help="Use the selected variant's merged ZIP"
    )
    args = parser.parse_args()
    print(prepare(args.variant, args.cache, args.archive))

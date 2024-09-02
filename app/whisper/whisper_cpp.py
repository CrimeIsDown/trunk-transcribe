from csv import DictReader
import os
import subprocess

from .base import BaseWhisper, WhisperResult


class WhisperCpp(BaseWhisper):
    def __init__(self, model_name: str, model_dir: str):
        model_path = f"{model_dir}/ggml-{model_name}.bin"
        if os.path.isfile(model_path):
            self.model_path = model_path

    def transcribe(
        self,
        audio: str,
        language: str = "en",
        initial_prompt: str | None = None,
        vad_filter: bool = False,
        **decode_options,
    ) -> WhisperResult:
        args = [
            "whisper-cpp",
            "--model",
            self.model_path,
            "--language",
            language,
            "--output-csv",
        ]

        if initial_prompt:
            args += ["--prompt", initial_prompt]

        if "best_of" in decode_options and decode_options["best_of"]:
            args += ["--best-of", str(decode_options["best_of"])]

        if "beam_size" in decode_options and decode_options["beam_size"]:
            args += ["--beam-size", str(decode_options["beam_size"])]

        args.append(audio)

        p = subprocess.run(args)
        p.check_returncode()

        result: WhisperResult = {"segments": [], "text": "", "language": language}

        with open(f"{audio}.csv", newline="") as csvfile:
            transcript = DictReader(csvfile)
            for line in transcript:
                # Handle quirks of whisper.cpp
                if (
                    len(line["text"])
                    and "[BLANK_AUDIO]" not in line["text"]
                    and "[SOUND]" not in line["text"]
                ):
                    result["segments"].append(
                        {
                            "start": float(line["start"]) / 1000,
                            "end": float(line["end"]) / 1000,
                            "text": line["text"],
                        }
                    )
        os.unlink(f"{audio}.csv")

        if len(result["segments"]):
            result["text"] = "\n".join(
                [segment["text"] for segment in result["segments"]]
            )

        return result

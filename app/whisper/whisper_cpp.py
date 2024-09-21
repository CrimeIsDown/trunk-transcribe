from csv import DictReader
import os
import subprocess

from .base import BaseWhisper, TranscribeOptions, WhisperResult


class WhisperCpp(BaseWhisper):
    def __init__(self, model_name: str, model_dir: str):
        model_path = f"{model_dir}/ggml-{model_name}.bin"
        if os.path.isfile(model_path):
            self.model_path = model_path
        else:
            raise FileNotFoundError(f"Model file not found: {model_path}")

    def transcribe(
        self,
        audio: str,
        options: TranscribeOptions,
        language: str = "en",
    ) -> WhisperResult:
        args = [
            "whisper-cpp",
            "--model",
            self.model_path,
            "--language",
            language,
            "--output-csv",
        ]

        if options["initial_prompt"]:
            args += ["--prompt", options["initial_prompt"]]

        if (
            "best_of" in options["decode_options"]
            and options["decode_options"]["best_of"]
        ):
            args += ["--best-of", str(options["decode_options"]["best_of"])]

        if (
            "beam_size" in options["decode_options"]
            and options["decode_options"]["beam_size"]
        ):
            args += ["--beam-size", str(options["decode_options"]["beam_size"])]

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

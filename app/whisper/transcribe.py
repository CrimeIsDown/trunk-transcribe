import json
import logging
import os
import time


from .base import TranscribeOptions, WhisperResult, BaseWhisper
from .exceptions import WhisperException
from .config import TranscriptCleanupConfig


def transcribe(
    model: BaseWhisper,
    audio_file: str,
    options: TranscribeOptions,
    language: str = "en",
) -> WhisperResult:
    logging.debug(
        f'Transcribing {audio_file} with language="{language}", initial_prompt="{options["initial_prompt"]}", vad_filter={options["vad_filter"]}'
    )

    # measure transcription time
    start_time = time.time()

    try:
        result = model.transcribe(
            audio_file,
            options,
            language=language,
        )
    finally:
        os.unlink(audio_file)
    logging.debug(f"{audio_file} transcription result: " + json.dumps(result, indent=4))

    end_time = time.time()
    execution_time = end_time - start_time
    logging.debug(f"Transcription execution time: {execution_time} seconds")

    return (
        cleanup_transcript(result, options["cleanup_config"])
        if options["cleanup"]
        else result
    )


# Commented out until this can be revisited
# def transcribe_bulk(
#     model: BaseWhisper,
#     audio_files: list[str],
#     initial_prompts: list[str] = [],
#     cleanup: bool = False,
#     vad_filter: bool = False,
#     cleanup_config: TranscriptCleanupConfig = [],
# ) -> list[WhisperResult | None]:
#     # measure transcription time
#     start_time = time.time()

#     try:
#         results = model.transcribe_bulk(
#             audio_files=audio_files,
#             initial_prompts=initial_prompts,
#             vad_filter=vad_filter,
#         )
#     finally:
#         for audio_file in audio_files:
#             os.unlink(audio_file)
#     logging.debug(
#         f"{audio_files} transcription result: " + json.dumps(results, indent=4)
#     )

#     end_time = time.time()
#     execution_time = end_time - start_time
#     logging.debug(f"Transcription execution time: {execution_time} seconds")

#     if cleanup:
#         cleaned_results: list[WhisperResult | None] = []
#         for result in results:
#             try:
#                 cleaned_results.append(cleanup_transcript(result, cleanup_config))
#             except WhisperException:
#                 cleaned_results.append(None)
#         return cleaned_results
#     return results  # type: ignore


def cleanup_transcript(
    result: WhisperResult, config: TranscriptCleanupConfig
) -> WhisperResult:
    indices_to_delete = set()

    hallucination_count = 0
    # Check for patterns to replace or delete
    for i, segment in enumerate(result["segments"]):
        for item in config:
            if item["match_type"] == "partial":
                is_match = item["pattern"].lower() in segment["text"].lower().strip()
            elif item["match_type"] == "full":
                is_match = item["pattern"].lower() == segment["text"].lower().strip()
            else:
                raise Exception("Unsupported match_type in config")

            if is_match:
                if item["is_hallucination"]:
                    hallucination_count += 1
                if item["action"] == "delete":
                    indices_to_delete.add(i)
                elif item["action"] == "replace":
                    if item["match_type"] == "partial":
                        segment["text"] = segment["text"].replace(
                            item["pattern"], item["replacement"]
                        )
                    elif item["match_type"] == "full":
                        segment["text"] = item["replacement"]
                break
    # Do not proceed any further if the entire transcript appears to be hallucinations
    if len(result["segments"]) == hallucination_count:
        raise WhisperException("Transcript invalid, 100% hallucination")

    prev_seg_text = ""
    times_seg_repeated = 0
    # Check for repeated segments
    for i, segment in enumerate(result["segments"]):
        if prev_seg_text == segment["text"]:
            times_seg_repeated += 1
            # Delete all the repetitive segments (except for the first instance)
            # until we find a non-repetitive one or we reach the end of the file
            if times_seg_repeated == 2:
                for j in range(i - times_seg_repeated, i):
                    indices_to_delete.add(j)
            elif times_seg_repeated > 2:
                indices_to_delete.add(i)
        else:
            times_seg_repeated = 0
            prev_seg_text = segment["text"]

    # Delete the invalid segments from the transcript
    valid_segments = [
        segment
        for i, segment in enumerate(result["segments"])
        if i not in indices_to_delete
    ]

    result["segments"] = valid_segments
    result["text"] = "\n".join([segment["text"] for segment in valid_segments])

    return result

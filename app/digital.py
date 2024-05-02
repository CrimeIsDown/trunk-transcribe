from threading import Lock

from .metadata import Metadata, SrcListItem
from .transcript import Transcript
from .whisper import WhisperSegment, transcribe


def get_closest_src(srcList: list[SrcListItem], segment: WhisperSegment):
    def closest_source(src):
        return abs(src["pos"] - segment["start"])

    closest_src = min(srcList, key=closest_source)
    return closest_src


# TODO: write tests
def transcribe_call(
    model, model_lock: Lock, audio_file: str, metadata: Metadata
) -> Transcript:
    transcript = Transcript()

    prev_transcript = ""

    for src in metadata["srcList"]:
        if (
            len(src.get("transcript_prompt", ""))
            and src["transcript_prompt"] not in prev_transcript
        ):
            prev_transcript += " " + src["transcript_prompt"]

    response = transcribe(
        model=model,
        model_lock=model_lock,
        audio_file=audio_file,
        initial_prompt=prev_transcript,
        cleanup=True,
    )

    for segment in response["segments"]:
        transcript.append(
            segment["text"].strip(),
            # Finding the closest source based on the segment start time
            get_closest_src(metadata["srcList"], segment),
        )

    return transcript.validate()

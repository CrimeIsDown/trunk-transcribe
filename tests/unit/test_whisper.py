import unittest
import csv
import json
from app.exceptions import WhisperException
from app.transcript import RawTranscript
from app.whisper.transcribe import WhisperResult, cleanup_transcript


class TestTranscript(unittest.TestCase):
    def _transform_into_whisper_result(
        self, raw_transcript: RawTranscript
    ) -> WhisperResult:
        result = {"text": "", "segments": [], "language": "en"}
        pos = 0
        for _, transcript in raw_transcript:
            for segment in transcript.splitlines():
                endpos = pos + 1
                result["segments"].append(
                    {"start": pos, "end": endpos, "text": segment}
                )
                result["text"] += segment + "\n"

        result["text"] = result["text"].strip()

        return result  # type: ignore

    def test_transcript_cleanup_on_hallucinations(self):
        with open("tests/data/hallucinations.json") as file:
            hallucinations = json.load(file)

        for h in hallucinations:
            with self.assertRaises(WhisperException):
                whisperresult = {
                    "text": "\n".join(h),
                    "segments": [
                        {"start": 0, "end": 0, "text": segment} for segment in h
                    ],
                }
                cleanup_transcript(whisperresult)  # type: ignore

    def test_transcript_cleanup_on_dataset(self):
        with open(
            "tests/data/hallucination_transcript_export.csv", newline=""
        ) as csvfile:
            reader = csv.DictReader(csvfile)
            row_count = 0
            edited_count = 0
            hallucination_count = 0
            for row in reader:
                row_count += 1
                raw_transcript = json.loads(row["raw_transcript"])
                original_result = self._transform_into_whisper_result(raw_transcript)
                original_text = original_result["text"]

                try:
                    transformed_result = cleanup_transcript(original_result)
                    if original_text != transformed_result["text"]:
                        edited_count += 1
                except WhisperException:
                    hallucination_count += 1

            # Row count: 12790 / Edited count: 1655 / Full hallucination count: 3378
            self.assertGreater(row_count, hallucination_count)
            self.assertGreater(hallucination_count, edited_count)


if __name__ == "__main__":
    unittest.main()

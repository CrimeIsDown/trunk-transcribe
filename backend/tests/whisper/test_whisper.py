import unittest
import csv
import json
from app.utils.cache import get_ttl_hash
from app.whisper.config import get_transcript_cleanup_config
from app.whisper.exceptions import WhisperException
from app.models.transcript import RawTranscript
from app.whisper.transcribe import WhisperResult, cleanup_transcript


transcript_cleanup_config = get_transcript_cleanup_config(
    get_ttl_hash(cache_seconds=60)
)


class TestTranscript(unittest.TestCase):
    def _transform_into_whisper_result(
        self, raw_transcript: RawTranscript
    ) -> WhisperResult:
        result: WhisperResult = {"text": "", "segments": [], "language": "en"}
        pos = 0
        for _, transcript in raw_transcript:
            for segment in transcript.splitlines():
                endpos = pos + 1
                result["segments"].append(
                    {"start": pos, "end": endpos, "text": segment}
                )
                result["text"] += segment + "\n"

        result["text"] = result["text"].strip()

        return result

    def test_transcript_cleanup_on_hallucinations(self):
        with open("tests/data/hallucinations.json") as file:
            hallucinations = json.load(file)

        for h in hallucinations:
            with self.assertRaises(WhisperException):
                whisperresult: WhisperResult = {
                    "language": "en",
                    "text": "\n".join(h),
                    "segments": [
                        {"start": 0, "end": 0, "text": segment} for segment in h
                    ],
                }
                cleanup_transcript(whisperresult, transcript_cleanup_config)

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
                    transformed_result = cleanup_transcript(
                        original_result, transcript_cleanup_config
                    )
                    if original_text != transformed_result["text"]:
                        edited_count += 1
                except WhisperException:
                    hallucination_count += 1

            # Row count: 12790 / Edited count: 1655 / Full hallucination count: 3378
            self.assertGreater(row_count, hallucination_count)
            self.assertGreater(hallucination_count, edited_count)


class TestCleanupTranscriptReplace(unittest.TestCase):
    """Tests for the 'replace' action in cleanup_transcript()."""

    def _make_result(self, segments: list[str]) -> WhisperResult:
        return {
            "language": "en",
            "text": "\n".join(segments),
            "segments": [
                {"start": i, "end": i + 1, "text": s} for i, s in enumerate(segments)
            ],
        }

    def test_partial_replace_substitutes_substring(self):
        """Partial match with replace action substitutes the matched substring."""
        config = [
            {
                "pattern": "badword",
                "replacement": "***",
                "match_type": "partial",
                "action": "replace",
                "is_hallucination": False,
            }
        ]
        result = self._make_result(["This is a badword example"])
        cleaned = cleanup_transcript(result, config)
        self.assertEqual(cleaned["segments"][0]["text"], "This is a *** example")
        self.assertIn("***", cleaned["text"])

    def test_full_replace_substitutes_entire_segment(self):
        """Full match with replace action replaces the entire segment text."""
        config = [
            {
                "pattern": "replace me entirely",
                "replacement": "clean text",
                "match_type": "full",
                "action": "replace",
                "is_hallucination": False,
            }
        ]
        result = self._make_result(["replace me entirely"])
        cleaned = cleanup_transcript(result, config)
        self.assertEqual(cleaned["segments"][0]["text"], "clean text")
        self.assertEqual(cleaned["text"], "clean text")

    def test_full_replace_is_case_insensitive_on_match(self):
        """Full match comparison is case-insensitive (matching behavior from source)."""
        config = [
            {
                "pattern": "Replace Me Entirely",
                "replacement": "clean text",
                "match_type": "full",
                "action": "replace",
                "is_hallucination": False,
            }
        ]
        result = self._make_result(["replace me entirely"])
        cleaned = cleanup_transcript(result, config)
        self.assertEqual(cleaned["segments"][0]["text"], "clean text")

    def test_partial_replace_does_not_affect_non_matching_segments(self):
        """Replace action only affects segments that match the pattern."""
        config = [
            {
                "pattern": "badword",
                "replacement": "***",
                "match_type": "partial",
                "action": "replace",
                "is_hallucination": False,
            }
        ]
        result = self._make_result(
            ["All clear here", "badword spotted", "Nothing here"]
        )
        cleaned = cleanup_transcript(result, config)
        self.assertEqual(cleaned["segments"][0]["text"], "All clear here")
        self.assertEqual(cleaned["segments"][1]["text"], "*** spotted")
        self.assertEqual(cleaned["segments"][2]["text"], "Nothing here")

    def test_replace_hallucination_all_segments_raises(self):
        """If every segment is a replace+hallucination match, WhisperException is raised."""
        config = [
            {
                "pattern": "hallucinated phrase",
                "replacement": "",
                "match_type": "full",
                "action": "replace",
                "is_hallucination": True,
            }
        ]
        result = self._make_result(["hallucinated phrase"])
        with self.assertRaises(WhisperException):
            cleanup_transcript(result, config)

    def test_replace_hallucination_partial_segments_does_not_raise(self):
        """If only some segments are hallucinations, no exception is raised."""
        config = [
            {
                "pattern": "hallucinated phrase",
                "replacement": "",
                "match_type": "full",
                "action": "replace",
                "is_hallucination": True,
            }
        ]
        result = self._make_result(["hallucinated phrase", "real transmission content"])
        cleaned = cleanup_transcript(result, config)
        # Both segments remain (replace doesn't delete)
        self.assertEqual(len(cleaned["segments"]), 2)

    def test_cleanup_transcript_empty_segments_returns_empty_result(self):
        result: WhisperResult = {
            "language": "en",
            "text": "",
            "segments": [],
        }
        cleaned = cleanup_transcript(result, [])
        self.assertEqual(result, cleaned)


if __name__ == "__main__":
    unittest.main()

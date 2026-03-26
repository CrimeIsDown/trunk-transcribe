import unittest

from app.radio.digital import process_response
from app.models.transcript import Transcript
from app.whisper.exceptions import WhisperException


def _make_src(src_id: int, pos: float, tag: str = "") -> dict:
    return {
        "src": src_id,
        "time": 100,
        "pos": pos,
        "emergency": 0,
        "signal_system": "sys",
        "tag": tag,
        "transcript_prompt": "",
    }


class TestDigitalProcessResponse(unittest.TestCase):
    def test_process_response_assigns_closest_src_to_each_segment(self):
        metadata = {
            "srcList": [
                _make_src(100, 0.0, "Alpha"),
                _make_src(200, 3.0, "Bravo"),
            ]
        }
        response = {
            "text": "hello world",
            "segments": [
                {"text": " Hello", "start": 0.5, "end": 1.5},
                {"text": " world", "start": 3.2, "end": 4.0},
            ],
        }

        result = process_response(response, metadata)

        self.assertEqual(2, len(result.transcript))
        # First segment is closest to src 100 (pos 0.0)
        self.assertEqual(100, result.transcript[0][0]["src"])
        self.assertEqual("Hello", result.transcript[0][1])
        # Second segment is closest to src 200 (pos 3.0)
        self.assertEqual(200, result.transcript[1][0]["src"])
        self.assertEqual("world", result.transcript[1][1])

    def test_process_response_strips_whitespace_from_segments(self):
        metadata = {"srcList": [_make_src(100, 0.0, "Alpha")]}
        response = {
            "text": "  hello  ",
            "segments": [{"text": "  hello  ", "start": 0.0, "end": 1.0}],
        }

        result = process_response(response, metadata)

        self.assertEqual("hello", result.transcript[0][1])

    def test_process_response_raises_on_empty_result(self):
        metadata = {"srcList": [_make_src(100, 0.0)]}
        response = {
            "text": "",
            "segments": [{"text": "", "start": 0.0, "end": 1.0}],
        }

        with self.assertRaises(WhisperException):
            process_response(response, metadata)

    def test_process_response_raises_on_too_short_result(self):
        metadata = {"srcList": [_make_src(100, 0.0)]}
        response = {
            "text": "hi",
            "segments": [{"text": "hi", "start": 0.0, "end": 0.5}],
        }

        with self.assertRaises(WhisperException):
            process_response(response, metadata)

    def test_process_response_multiple_segments_single_src(self):
        metadata = {"srcList": [_make_src(100, 0.0, "Dispatch")]}
        response = {
            "text": "engine 96 on scene all units copy",
            "segments": [
                {"text": " Engine 96 on scene", "start": 0.0, "end": 2.0},
                {"text": " all units copy", "start": 2.0, "end": 4.0},
            ],
        }

        result = process_response(response, metadata)

        self.assertEqual(2, len(result.transcript))
        for src, text in result.transcript:
            self.assertEqual(100, src["src"])


if __name__ == "__main__":
    unittest.main()

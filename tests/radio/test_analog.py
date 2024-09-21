from multiprocessing import process
import unittest
from unittest.mock import Mock, patch
from threading import Lock

from app.radio.analog import process_response
from app.models.transcript import Transcript


class TestAnalog(unittest.TestCase):
    def setUp(self):
        self.model = Mock()
        self.model_lock = Lock()
        self.audio_file = "test_audio.wav"
        self.response = {
            "text": " Hello\n world",
            "segments": [
                {"text": " Hello", "start": 0, "end": 2},
                {"text": " world", "start": 2, "end": 5},
            ],
        }

    def test_process_response(self):
        expected_transcript = Transcript()
        expected_transcript.append("Hello")
        expected_transcript.append("world")

        result = process_response(self.response, {}) # type: ignore

        self.assertEqual(expected_transcript.json, result.json)


if __name__ == "__main__":
    unittest.main()

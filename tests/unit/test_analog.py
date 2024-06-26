import unittest
from unittest.mock import Mock, patch
from threading import Lock

from app.analog import transcribe_call
from app.transcript import Transcript


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

    @patch("app.analog.transcribe")
    def test_transcribe_call(self, mock_transcribe):
        mock_transcribe.return_value = self.response

        expected_transcript = Transcript()
        expected_transcript.append("Hello")
        expected_transcript.append("world")

        result = transcribe_call(self.model, self.model_lock, self.audio_file)

        mock_transcribe.assert_called_once_with(
            model=self.model,
            model_lock=self.model_lock,
            audio_file=self.audio_file,
            cleanup=True,
            vad_filter=True,
            initial_prompt="",
        )

        self.assertEqual(expected_transcript.json, result.json)


if __name__ == "__main__":
    unittest.main()

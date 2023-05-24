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

    @patch("app.analog.pad_silence")
    @patch("app.analog.transcribe")
    def test_transcribe_call(self, mock_transcribe, mock_pad_silence):
        mock_pad_silence.return_value = "padded_audio.wav"
        mock_transcribe.return_value = self.response

        expected_transcript = Transcript()
        expected_transcript.append("Hello")
        expected_transcript.append("world")

        result = transcribe_call(self.model, self.model_lock, self.audio_file)

        mock_pad_silence.assert_called_once_with(self.audio_file)
        mock_transcribe.assert_called_once_with(
            model=self.model,
            model_lock=self.model_lock,
            audio_file="padded_audio.wav",
        )

        self.assertEqual(expected_transcript.json, result.json)


if __name__ == "__main__":
    unittest.main()

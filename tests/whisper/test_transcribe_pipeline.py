import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from app.whisper.transcribe import transcribe


def build_options(cleanup: bool = True) -> dict:
    return {
        "initial_prompt": "alpha bravo",
        "cleanup": cleanup,
        "vad_filter": False,
        "decode_options": {"beam_size": 5},
        "cleanup_config": [],
    }


class TestTranscribePipeline(unittest.TestCase):
    def test_transcribe_deletes_audio_file_and_cleans_up_when_enabled(self):
        model = Mock()
        raw_result = {
            "text": "hello",
            "segments": [{"start": 0.0, "end": 0.5, "text": "hello"}],
            "language": "en",
        }
        cleaned_result = {
            "text": "hello cleaned",
            "segments": [{"start": 0.0, "end": 0.5, "text": "hello cleaned"}],
            "language": "en",
        }
        model.transcribe.return_value = raw_result

        with tempfile.NamedTemporaryFile(delete=False) as temp_audio:
            audio_path = temp_audio.name

        with patch(
            "app.whisper.transcribe.cleanup_transcript", return_value=cleaned_result
        ) as cleanup_transcript_mock:
            result = transcribe(
                model=model,
                audio_file=audio_path,
                options=build_options(cleanup=True),
                language="es",
            )

        self.assertEqual(cleaned_result, result)
        model.transcribe.assert_called_once_with(
            audio_path, build_options(cleanup=True), language="es"
        )
        cleanup_transcript_mock.assert_called_once_with(raw_result, [])
        self.assertFalse(os.path.exists(audio_path))

    def test_transcribe_deletes_audio_file_without_cleanup_when_disabled(self):
        model = Mock()
        raw_result = {
            "text": "hello",
            "segments": [{"start": 0.0, "end": 0.5, "text": "hello"}],
            "language": "en",
        }
        model.transcribe.return_value = raw_result

        with tempfile.NamedTemporaryFile(delete=False) as temp_audio:
            audio_path = temp_audio.name

        with patch("app.whisper.transcribe.cleanup_transcript") as cleanup_mock:
            result = transcribe(
                model=model,
                audio_file=audio_path,
                options=build_options(cleanup=False),
            )

        self.assertEqual(raw_result, result)
        cleanup_mock.assert_not_called()
        self.assertFalse(os.path.exists(audio_path))

    def test_transcribe_deletes_audio_file_when_model_raises(self):
        model = Mock()
        model.transcribe.side_effect = RuntimeError("transcribe failed")

        with tempfile.NamedTemporaryFile(delete=False) as temp_audio:
            audio_path = temp_audio.name

        with self.assertRaisesRegex(RuntimeError, "transcribe failed"):
            transcribe(
                model=model,
                audio_file=audio_path,
                options=build_options(cleanup=False),
            )

        self.assertFalse(os.path.exists(audio_path))


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import MagicMock, patch

from app import worker


class TestWorkerRouting(unittest.TestCase):
    def test_get_transcription_queue_defaults_to_whisper(self):
        with patch.dict("os.environ", {"DEFAULT_TRANSCRIPTION_BACKEND": "whisper"}):
            self.assertEqual("transcribe_whisper", worker.get_transcription_queue())

    def test_get_transcription_queue_maps_known_backends(self):
        self.assertEqual("transcribe_whisper", worker.get_transcription_queue("whisper"))
        self.assertEqual("transcribe_qwen", worker.get_transcription_queue("qwen"))
        self.assertEqual("transcribe_voxtral", worker.get_transcription_queue("voxtral"))

    def test_get_transcription_queue_rejects_unknown_backend(self):
        with self.assertRaisesRegex(ValueError, "Unsupported transcription backend"):
            worker.get_transcription_queue("unknown")

    def test_queue_task_routes_to_backend_queue_and_post_queue(self):
        transcribe_signature = MagicMock()
        transcribe_signature.set.return_value = transcribe_signature
        post_signature = MagicMock()
        post_signature.set.return_value = post_signature
        chain_result = MagicMock()
        chain_result.apply_async.return_value = "queued"
        transcribe_signature.__or__.return_value = chain_result

        options = {
            "initial_prompt": "",
            "cleanup": False,
            "vad_filter": False,
            "decode_options": {},
            "cleanup_config": [],
        }

        with patch("app.worker.transcribe_task.s", return_value=transcribe_signature):
            with patch(
                "app.worker.post_transcribe_task.s", return_value=post_signature
            ):
                result = worker.queue_task(
                    "https://example.com/audio.wav",
                    {"audio_type": "analog"},
                    options,
                    transcription_backend="qwen",
                )

        self.assertEqual("queued", result)
        transcribe_signature.set.assert_called_once_with(queue="transcribe_qwen")
        post_signature.set.assert_called_once_with(queue="post_transcribe")
        chain_result.apply_async.assert_called_once_with()

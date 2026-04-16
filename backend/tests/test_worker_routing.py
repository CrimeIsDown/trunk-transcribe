import unittest
from unittest.mock import MagicMock, patch

from app import worker
from app.core.transcription_profiles import build_pool_profile, build_vendor_profile


def build_metadata(audio_type: str = "analog") -> dict:
    return {
        "freq": 1,
        "start_time": 1700000000,
        "stop_time": 1700000005,
        "call_length": 5.0,
        "talkgroup": 1,
        "talkgroup_tag": "tag",
        "talkgroup_description": "desc",
        "talkgroup_group_tag": "group-tag",
        "talkgroup_group": "group",
        "audio_type": audio_type,
        "short_name": "short",
        "emergency": 0,
        "encrypted": 0,
        "freqList": [],
        "srcList": [],
    }


class TestWorkerRouting(unittest.TestCase):
    def tearDown(self):
        worker.search_adapters = []

    def test_get_transcription_queue_defaults_to_local_whisper_pool(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                "transcribe.remote.pool.local.whisper.large-v3",
                worker.get_transcription_queue(),
            )

    def test_get_transcription_queue_routes_vendor_profiles(self):
        self.assertEqual(
            "transcribe.remote.vendor",
            worker.get_transcription_queue(
                build_vendor_profile("openai", "whisper-1")
            ),
        )

    def test_get_transcription_queue_routes_pool_profiles(self):
        self.assertEqual(
            "transcribe.remote.pool.vast.whisper.large-v3",
            worker.get_transcription_queue(
                build_pool_profile(
                    platform="vast",
                    family="whisper",
                    variant="large-v3",
                    provider="speaches",
                    model="Systran/faster-whisper-large-v3",
                )
            ),
        )

    def test_queue_task_routes_to_profile_queue_and_post_queue(self):
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
        profile = build_pool_profile(
            platform="vast",
            family="whisper",
            variant="large-v3",
            provider="speaches",
            model="Systran/faster-whisper-large-v3",
        )

        with patch("app.worker.transcribe_task.s", return_value=transcribe_signature):
            with patch(
                "app.worker.post_transcribe_task.s", return_value=post_signature
            ):
                result = worker.queue_task(
                    "https://example.com/audio.wav",
                    {"audio_type": "analog"},
                    options,
                    transcription_profile=profile,
                )

        self.assertEqual("queued", result)
        transcribe_signature.set.assert_called_once_with(
            queue="transcribe.remote.pool.vast.whisper.large-v3"
        )
        post_signature.set.assert_called_once_with(queue="post_transcribe")
        chain_result.apply_async.assert_called_once_with()

    def test_queue_task_routes_vendor_jobs_to_vendor_queue(self):
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
                    transcription_profile=build_vendor_profile(
                        "deepinfra", "openai/whisper-large-v3-turbo"
                    ),
                )

        self.assertEqual("queued", result)
        transcribe_signature.set.assert_called_once_with(
            queue="transcribe.remote.vendor"
        )
        post_signature.set.assert_called_once_with(queue="post_transcribe")
        chain_result.apply_async.assert_called_once_with()

    def test_post_transcribe_task_patches_and_indexes_enriched_metadata(self):
        search_adapter = MagicMock()
        search_adapter.index_call.return_value = "https://search.example/call"
        worker.search_adapters = [search_adapter]

        result = {
            "result": {
                "text": "hello world",
                "segments": [{"start": 0.0, "end": 1.0, "text": "hello world"}],
                "language": "en",
            },
            "transcription_provider": "openai",
            "transcription_model": "whisper-1",
        }
        metadata = build_metadata()
        geo = {"geo": {"lat": 1.0, "lng": 2.0}, "geo_formatted_address": "123 Main"}

        with patch("app.worker.api_client.call") as api_call_mock:
            with patch("app.geocoding.geocoding.lookup_geo", return_value=geo):
                with patch("app.notifications.notification.send_notifications"):
                    transcript_text = worker.post_transcribe_task.run(
                        result,
                        metadata,
                        "https://example.com/audio.wav",
                        id=42,
                    )

        self.assertEqual("hello world", transcript_text)
        api_call_mock.assert_called_once()
        self.assertEqual("patch", api_call_mock.call_args.args[0])
        self.assertEqual("calls/42", api_call_mock.call_args.args[1])
        self.assertEqual(
            "openai",
            api_call_mock.call_args.kwargs["json"]["raw_metadata"][
                "transcription_provider"
            ],
        )
        self.assertEqual(
            "whisper-1",
            api_call_mock.call_args.kwargs["json"]["raw_metadata"][
                "transcription_model"
            ],
        )
        indexed_metadata = search_adapter.index_call.call_args.args[1]
        self.assertEqual("openai", indexed_metadata["transcription_provider"])
        self.assertEqual("whisper-1", indexed_metadata["transcription_model"])


if __name__ == "__main__":
    unittest.main()

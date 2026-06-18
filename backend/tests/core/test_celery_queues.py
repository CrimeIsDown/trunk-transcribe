import unittest

from app.core.celery_queues import default_celery_queues
from app.core.transcription_profiles import build_pool_profile, build_vendor_profile


class TestDefaultCeleryQueues(unittest.TestCase):
    def test_uses_explicit_profile_queue(self):
        self.assertEqual(
            "transcribe.model.whisper-large-v3-turbo",
            default_celery_queues(
                explicit_profile=build_vendor_profile(
                    "deepinfra",
                    "openai/whisper-large-v3-turbo",
                    "whisper-large-v3-turbo",
                ),
                default_profile=build_vendor_profile("openai", "whisper-1", "whisper-1"),
            ),
        )

    def test_uses_default_profile_when_explicit_profile_is_missing(self):
        self.assertEqual(
            "transcribe.model.whisper-large-v3",
            default_celery_queues(
                explicit_profile=None,
                default_profile=build_pool_profile(
                    platform="local",
                    family="whisper",
                    variant="large-v3",
                    provider="speaches",
                    model="Systran/faster-whisper-large-v3",
                    model_key="whisper-large-v3",
                ),
            ),
        )

    def test_can_include_post_transcribe_queue(self):
        self.assertEqual(
            "transcribe.model.whisper-1,post_transcribe",
            default_celery_queues(
                explicit_profile=build_vendor_profile("openai", "whisper-1", "whisper-1"),
                default_profile=None,
                include_post_transcribe=True,
            ),
        )


if __name__ == "__main__":
    unittest.main()

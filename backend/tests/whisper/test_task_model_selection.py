import os
import unittest
from unittest.mock import Mock, PropertyMock, patch

from app.core.transcription_profiles import build_pool_profile, build_vendor_profile
from app.whisper.task import TranscriptionTask


class TestTranscriptionTaskModelSelection(unittest.TestCase):
    def setUp(self):
        TranscriptionTask._models = {}
        self.task = TranscriptionTask()

    def test_default_profile_uses_local_whisper_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                "kind=pool;provider=speaches;model=Systran/faster-whisper-large-v3;platform=local;family=whisper;variant=large-v3",
                self.task.default_profile,
            )

    def test_resolve_profile_uses_explicit_vendor_profile(self):
        profile = self.task.resolve_profile(build_vendor_profile("openai", "whisper-1"))
        self.assertEqual("vendor", profile.kind)
        self.assertEqual("openai", profile.provider)
        self.assertEqual("whisper-1", profile.model)

    def test_resolve_profile_uses_explicit_pool_profile(self):
        profile = self.task.resolve_profile(
            build_pool_profile(
                platform="vast",
                family="whisper",
                variant="large-v3",
                provider="speaches",
                model="Systran/faster-whisper-large-v3",
            )
        )
        self.assertEqual("pool", profile.kind)
        self.assertEqual("vast", profile.platform)
        self.assertEqual("large-v3", profile.variant)

    def test_resolve_provider_and_model_for_vendor(self):
        self.assertEqual(
            ("openai", "whisper-1"),
            self.task.resolve_provider_and_model(
                build_vendor_profile("openai", "whisper-1")
            ),
        )

    def test_model_uses_default_profile_when_not_provided(self):
        expected_model = Mock()
        with patch.object(
            TranscriptionTask,
            "default_profile",
            new_callable=PropertyMock,
            return_value=build_vendor_profile("openai", "whisper-1"),
        ):
            with patch.object(
                self.task, "initialize_model", return_value=expected_model
            ) as initialize_model_mock:
                model = self.task.model()
        self.assertIs(expected_model, model)
        initialize_model_mock.assert_called_once_with(
            build_vendor_profile("openai", "whisper-1")
        )

    def test_model_caches_initialized_models(self):
        expected_model = Mock()
        profile = build_vendor_profile("openai", "whisper-1")
        with patch.object(
            self.task, "initialize_model", return_value=expected_model
        ) as initialize_model_mock:
            model_1 = self.task.model(profile)
            model_2 = self.task.model(profile)

        self.assertIs(model_1, model_2)
        initialize_model_mock.assert_called_once_with(profile)

    def test_initialize_model_openai_requires_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY env must be set"):
                self.task.initialize_model(build_vendor_profile("openai", "whisper-1"))

    def test_initialize_model_deepinfra_requires_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                RuntimeError, "DEEPINFRA_API_KEY env must be set"
            ):
                self.task.initialize_model(
                    build_vendor_profile(
                        "deepinfra", "openai/whisper-large-v3-turbo"
                    )
                )


if __name__ == "__main__":
    unittest.main()

import os
import unittest
from unittest.mock import Mock, PropertyMock, patch

from app.whisper.task import WhisperTask


class TestWhisperTaskModelSelection(unittest.TestCase):
    def setUp(self):
        WhisperTask._models = {}
        self.task = WhisperTask()

    def test_default_implementation_requires_env(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                "whisper-asr-api:whisper-asr-webservice:small.en",
                self.task.default_implementation,
            )

    def test_default_implementation_openai_uses_whisper_1(self):
        with patch.dict(
            os.environ,
            {"WHISPER_IMPLEMENTATION": "openai", "WHISPER_MODEL": "custom-model"},
            clear=True,
        ):
            self.assertEqual("openai:whisper-1", self.task.default_implementation)

    def test_default_implementation_deepgram_uses_default_model(self):
        with patch.dict(os.environ, {"WHISPER_IMPLEMENTATION": "deepgram"}, clear=True):
            self.assertEqual("deepgram:nova-2", self.task.default_implementation)

    def test_default_implementation_deepinfra_uses_default_model(self):
        with patch.dict(
            os.environ, {"WHISPER_IMPLEMENTATION": "deepinfra"}, clear=True
        ):
            self.assertEqual(
                "deepinfra:openai/whisper-large-v3-turbo",
                self.task.default_implementation,
            )

    def test_default_implementation_whisper_uses_asr_api_by_default(self):
        with patch.dict(
            os.environ,
            {"ASR_PROVIDER": "whisper-asr-webservice", "ASR_MODEL": "large-v3"},
            clear=True,
        ):
            self.assertEqual(
                "whisper-asr-api:whisper-asr-webservice:large-v3",
                self.task.default_implementation,
            )

    def test_default_implementation_qwen_uses_generic_asr_api(self):
        with patch.dict(
            os.environ,
            {
                "TRANSCRIPTION_BACKEND": "qwen",
                "ASR_PROVIDER": "vllm",
                "ASR_MODEL": "qwen2.5-omni",
            },
            clear=True,
        ):
            self.assertEqual(
                "whisper-asr-api:vllm:qwen2.5-omni",
                self.task.default_implementation,
            )

    def test_default_implementation_voxtral_defaults_provider_and_model(self):
        with patch.dict(os.environ, {"TRANSCRIPTION_BACKEND": "voxtral"}, clear=True):
            self.assertEqual(
                "whisper-asr-api:voxtral:voxtral",
                self.task.default_implementation,
            )

    def test_default_implementation_rejects_removed_local_implementations(self):
        with patch.dict(
            os.environ, {"WHISPER_IMPLEMENTATION": "faster-whisper"}, clear=True
        ):
            with self.assertRaisesRegex(
                RuntimeError, "Local Whisper implementations have been removed"
            ):
                _ = self.task.default_implementation

    def test_model_uses_default_implementation_when_not_provided(self):
        expected_model = Mock()
        with patch.object(
            WhisperTask,
            "default_implementation",
            new_callable=PropertyMock,
            return_value="openai:whisper-1",
        ):
            with patch.object(
                self.task, "initialize_model", return_value=expected_model
            ) as initialize_model_mock:
                model = self.task.model()
        self.assertIs(expected_model, model)
        initialize_model_mock.assert_called_once_with("openai:whisper-1")

    def test_model_caches_initialized_models(self):
        expected_model = Mock()
        with patch.object(
            self.task, "initialize_model", return_value=expected_model
        ) as initialize_model_mock:
            model_1 = self.task.model("openai:whisper-1")
            model_2 = self.task.model("openai:whisper-1")

        self.assertIs(model_1, model_2)
        initialize_model_mock.assert_called_once_with("openai:whisper-1")

    def test_initialize_model_openai_requires_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY env must be set"):
                self.task.initialize_model("openai:whisper-1")

    def test_initialize_model_deepgram_requires_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                RuntimeError, "DEEPGRAM_API_KEY env must be set"
            ):
                self.task.initialize_model("deepgram:nova-2")

    def test_initialize_model_deepinfra_requires_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                RuntimeError, "DEEPINFRA_API_KEY env must be set"
            ):
                self.task.initialize_model("deepinfra:openai/whisper-large-v3-turbo")

    def test_initialize_model_unknown_implementation_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "Unknown implementation unknown"):
                self.task.initialize_model("unknown:model")


if __name__ == "__main__":
    unittest.main()

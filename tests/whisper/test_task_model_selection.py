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
            with self.assertRaisesRegex(
                RuntimeError, "WHISPER_IMPLEMENTATION env must be set"
            ):
                _ = self.task.default_implementation

    def test_default_implementation_openai_uses_whisper_1(self):
        with patch.dict(
            os.environ,
            {"WHISPER_IMPLEMENTATION": "openai", "WHISPER_MODEL": "custom-model"},
            clear=True,
        ):
            self.assertEqual("openai:whisper-1", self.task.default_implementation)

    def test_default_implementation_deepgram_uses_default_model(self):
        with patch.dict(
            os.environ, {"WHISPER_IMPLEMENTATION": "deepgram"}, clear=True
        ):
            self.assertEqual("deepgram:nova-2", self.task.default_implementation)

    def test_default_implementation_deepinfra_uses_default_model(self):
        with patch.dict(
            os.environ, {"WHISPER_IMPLEMENTATION": "deepinfra"}, clear=True
        ):
            self.assertEqual(
                "deepinfra:openai/whisper-large-v3-turbo",
                self.task.default_implementation,
            )

    def test_default_implementation_non_api_uses_configured_model(self):
        with patch.dict(
            os.environ,
            {"WHISPER_IMPLEMENTATION": "whisper", "WHISPER_MODEL": "tiny"},
            clear=True,
        ):
            self.assertEqual("whisper:tiny", self.task.default_implementation)

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

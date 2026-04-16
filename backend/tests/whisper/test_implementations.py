import os
import tempfile
import unittest
import wave
from unittest.mock import Mock, patch

from app.core.transcription_profiles import build_pool_profile, build_vendor_profile


def build_options(
    initial_prompt: str = "alpha bravo", vad_filter: bool = False
) -> dict:
    return {
        "initial_prompt": initial_prompt,
        "cleanup": False,
        "vad_filter": vad_filter,
        "decode_options": {"beam_size": 5},
        "cleanup_config": [],
    }


def create_tiny_wav(path: str) -> None:
    with wave.open(path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(8000)
        wav_file.writeframes(b"\x00\x00" * 800)


class TestWhisperImplementations(unittest.TestCase):
    def _assert_result_contract(self, result: dict):
        self.assertIn("text", result)
        self.assertIn("segments", result)
        self.assertIn("language", result)
        self.assertIsInstance(result["segments"], list)
        for segment in result["segments"]:
            self.assertIn("start", segment)
            self.assertIn("end", segment)
            self.assertIn("text", segment)

    def test_whisper_asr_api_openai_compatible_endpoint_structural_contract(self):
        from app.whisper.whisper_asr_api import WhisperAsrApi

        response = Mock()
        response.raise_for_status = Mock()
        response.json.return_value = {
            "text": "openai compatible asr",
            "segments": [{"start": 0.0, "end": 1.0, "text": "openai compatible asr"}],
        }

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            create_tiny_wav(temp_audio.name)
            audio_path = temp_audio.name

        try:
            implementation = WhisperAsrApi(
                base_url="http://localhost:8000/v1",
                model="qwen2.5-omni",
                provider="vllm",
            )
            implementation.client.post = Mock(return_value=response)
            result = implementation.transcribe(
                audio=audio_path, options=build_options(), language="es"
            )

            implementation.client.post.assert_called_once()
            call = implementation.client.post.call_args
            self.assertEqual(
                "http://localhost:8000/v1/audio/transcriptions", call.args[0]
            )
            self.assertEqual("qwen2.5-omni", call.kwargs["data"]["model"])
            self.assertEqual("verbose_json", call.kwargs["data"]["response_format"])
            self.assertEqual("alpha bravo", call.kwargs["data"]["prompt"])
            self.assertEqual({}, call.kwargs["headers"])
            self.assertEqual("es", result["language"])
            self._assert_result_contract(result)
        finally:
            os.unlink(audio_path)

    def test_whisper_asr_api_transcribe_structural_contract(self):
        from app.whisper.whisper_asr_api import WhisperAsrApi

        expected = {
            "text": "hello asr api",
            "segments": [{"start": 0.0, "end": 0.5, "text": "hello asr api"}],
            "language": "en",
        }
        response = Mock()
        response.raise_for_status = Mock()
        response.json.return_value = expected
        session = Mock()
        session.post.return_value = response

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            create_tiny_wav(temp_audio.name)
            audio_path = temp_audio.name

        try:
            with patch(
                "app.whisper.whisper_asr_api.requests.Session", return_value=session
            ):
                implementation = WhisperAsrApi(base_url="http://localhost:5000/v1")
                result = implementation.transcribe(
                    audio=audio_path,
                    options=build_options(vad_filter=False),
                    language="en",
                )

            kwargs = session.post.call_args.kwargs
            self.assertEqual(
                "http://localhost:5000/v1/audio/transcriptions",
                session.post.call_args.args[0],
            )
            self.assertEqual("alpha bravo", kwargs["data"]["prompt"])
            response.raise_for_status.assert_called_once()
            self.assertEqual(expected, result)
            self._assert_result_contract(result)
        finally:
            os.unlink(audio_path)

    def test_whisper_asr_api_synthesizes_segments_from_text_only_response(self):
        from app.whisper.whisper_asr_api import WhisperAsrApi

        response = Mock()
        response.raise_for_status = Mock()
        response.json.return_value = {
            "text": "first line\nsecond line",
            "language": "en",
        }
        session = Mock()
        session.post.return_value = response

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            create_tiny_wav(temp_audio.name)
            audio_path = temp_audio.name

        try:
            with patch(
                "app.whisper.whisper_asr_api.requests.Session", return_value=session
            ):
                implementation = WhisperAsrApi(base_url="http://localhost:5000/v1")
                result = implementation.transcribe(
                    audio=audio_path,
                    options=build_options(vad_filter=False),
                    language="en",
                )

            self.assertEqual("first line\nsecond line", result["text"])
            self.assertEqual(
                [
                    {"start": 0.0, "end": 1.0, "text": "first line"},
                    {"start": 1.0, "end": 2.0, "text": "second line"},
                ],
                result["segments"],
            )
            self.assertEqual("en", result["language"])
        finally:
            os.unlink(audio_path)

    def test_whisper_task_initialize_model_uses_http_adapter_for_openai(self):
        from app.whisper.task import TranscriptionTask
        from app.whisper.whisper_asr_api import WhisperAsrApi

        with patch.dict(os.environ, {"OPENAI_API_KEY": "openai-key"}, clear=True):
            implementation = TranscriptionTask().initialize_model(
                build_vendor_profile("openai", "whisper-1")
            )

        self.assertIsInstance(implementation, WhisperAsrApi)
        self.assertEqual("https://api.openai.com/v1", implementation.base_url)
        self.assertEqual("whisper-1", implementation.model)
        self.assertEqual({"Authorization": "Bearer openai-key"}, implementation.headers)

    def test_whisper_task_initialize_model_uses_http_adapter_for_deepinfra(self):
        from app.whisper.task import TranscriptionTask
        from app.whisper.whisper_asr_api import WhisperAsrApi

        with patch.dict(
            os.environ,
            {
                "DEEPINFRA_API_KEY": "deepinfra-key",
                "DEEPINFRA_BASE_URL": "https://example.com/v1/openai",
            },
            clear=True,
        ):
            implementation = TranscriptionTask().initialize_model(
                build_vendor_profile("deepinfra", "model-x")
            )

        self.assertIsInstance(implementation, WhisperAsrApi)
        self.assertEqual("https://example.com/v1/openai", implementation.base_url)
        self.assertEqual("model-x", implementation.model)
        self.assertEqual(
            {"Authorization": "Bearer deepinfra-key"}, implementation.headers
        )

    def test_transcription_task_initialize_model_uses_router_for_vast_pool(self):
        from app.whisper.task import TranscriptionTask
        from app.whisper.whisper_asr_api import WhisperAsrApi

        with patch.dict(
            os.environ,
            {"ASR_ROUTER_URL": "http://asr-router:8001/v1"},
            clear=True,
        ):
            implementation = TranscriptionTask().initialize_model(
                build_pool_profile(
                    platform="vast",
                    family="whisper",
                    variant="large-v3",
                    provider="speaches",
                    model="Systran/faster-whisper-large-v3",
                )
            )

        self.assertIsInstance(implementation, WhisperAsrApi)
        self.assertEqual("http://asr-router:8001/v1", implementation.base_url)
        self.assertEqual(
            {"X-ASR-Endpoint-Target": "pool.vast.whisper.large-v3"},
            implementation.headers,
        )


if __name__ == "__main__":
    unittest.main()

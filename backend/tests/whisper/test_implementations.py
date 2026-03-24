import os
import tempfile
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import Mock, patch


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

    def test_openai_api_transcribe_structural_contract(self):
        from app.whisper.openai import OpenAIApi

        expected = {
            "text": "hello world",
            "segments": [{"start": 0.0, "end": 1.0, "text": "hello world"}],
            "language": "es",
        }
        model_dump = Mock(return_value=expected)
        transcription_result = Mock(model_dump=model_dump)
        create_mock = Mock(return_value=transcription_result)
        client = Mock()
        client.audio.transcriptions.create = create_mock

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            create_tiny_wav(temp_audio.name)
            audio_path = temp_audio.name

        try:
            with patch("app.whisper.openai.OpenAI", return_value=client) as openai_mock:
                implementation = OpenAIApi(api_key="test-key")
                result = implementation.transcribe(
                    audio=audio_path, options=build_options(), language="es"
                )

            openai_mock.assert_called_once_with(api_key="test-key")
            kwargs = create_mock.call_args.kwargs
            self.assertEqual("whisper-1", kwargs["model"])
            self.assertEqual("verbose_json", kwargs["response_format"])
            self.assertEqual("es", kwargs["language"])
            self.assertIn("alpha bravo", kwargs["prompt"])
            self.assertEqual(expected, result)
            self._assert_result_contract(result)
        finally:
            os.unlink(audio_path)

    def test_deepinfra_api_transcribe_structural_contract(self):
        from app.whisper.deepinfra import DeepInfraApi

        expected = {
            "text": "hello from deepinfra",
            "segments": [{"start": 0.0, "end": 1.0, "text": "hello from deepinfra"}],
            "language": "en",
        }
        model_dump = Mock(return_value=expected)
        transcription_result = Mock(model_dump=model_dump)
        create_mock = Mock(return_value=transcription_result)
        client = Mock()
        client.audio.transcriptions.create = create_mock

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            create_tiny_wav(temp_audio.name)
            audio_path = temp_audio.name

        try:
            with patch.dict(
                os.environ,
                {"DEEPINFRA_BASE_URL": "https://example.com/v1/openai"},
                clear=False,
            ):
                with patch(
                    "app.whisper.deepinfra.OpenAI", return_value=client
                ) as openai_mock:
                    implementation = DeepInfraApi(
                        api_key="deepinfra-key", model="model-x"
                    )
                    result = implementation.transcribe(
                        audio=audio_path, options=build_options(), language="en"
                    )

            openai_mock.assert_called_once_with(
                api_key="deepinfra-key",
                base_url="https://example.com/v1/openai",
            )
            kwargs = create_mock.call_args.kwargs
            self.assertEqual("model-x", kwargs["model"])
            self.assertEqual("verbose_json", kwargs["response_format"])
            self.assertEqual("en", kwargs["language"])
            self.assertIn("alpha bravo", kwargs["prompt"])
            self.assertEqual(expected, result)
            self._assert_result_contract(result)
        finally:
            os.unlink(audio_path)

    def test_deepgram_api_transcribe_structural_contract(self):
        from app.whisper.deepgram import DeepgramApi

        utterance = SimpleNamespace(start=0.0, end=1.0, transcript="hello deepgram")
        response = SimpleNamespace(
            results=SimpleNamespace(
                utterances=[utterance],
                channels=[
                    SimpleNamespace(
                        alternatives=[SimpleNamespace(transcript="hello deepgram")]
                    )
                ],
            )
        )
        transcribe_file_mock = Mock(return_value=response)
        client = Mock()
        client.listen.prerecorded.v.return_value.transcribe_file = transcribe_file_mock

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            create_tiny_wav(temp_audio.name)
            audio_path = temp_audio.name

        try:
            with patch("app.whisper.deepgram.DeepgramClient", return_value=client):
                with patch(
                    "app.whisper.deepgram.PrerecordedOptions",
                    return_value={"options": "ok"},
                ) as options_mock:
                    implementation = DeepgramApi(api_key="deepgram-key", model="nova-2")
                    result = implementation.transcribe(
                        audio=audio_path, options=build_options(), language="en"
                    )

            self.assertEqual({"options": "ok"}, transcribe_file_mock.call_args.args[1])
            self.assertEqual(120, transcribe_file_mock.call_args.kwargs["timeout"])
            options_mock.assert_called_once()
            self.assertEqual("hello deepgram", result["text"])
            self.assertEqual("en", result["language"])
            self.assertEqual(1, len(result["segments"]))
            self._assert_result_contract(result)
        finally:
            os.unlink(audio_path)

    def test_deepgram_api_returns_empty_result_when_no_utterances(self):
        from app.whisper.deepgram import DeepgramApi

        response = SimpleNamespace(results=None)
        transcribe_file_mock = Mock(return_value=response)
        client = Mock()
        client.listen.prerecorded.v.return_value.transcribe_file = transcribe_file_mock

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            create_tiny_wav(temp_audio.name)
            audio_path = temp_audio.name

        try:
            with patch("app.whisper.deepgram.DeepgramClient", return_value=client):
                with patch("app.whisper.deepgram.PrerecordedOptions", return_value={}):
                    implementation = DeepgramApi(api_key="deepgram-key", model="nova-2")
                    result = implementation.transcribe(
                        audio=audio_path, options=build_options(), language="en"
                    )

            self.assertEqual({"segments": [], "text": "", "language": "en"}, result)
            self._assert_result_contract(result)
        finally:
            os.unlink(audio_path)

    def test_whisper_asr_api_legacy_endpoint_structural_contract(self):
        from app.whisper.whisper_asr_api import WhisperAsrApi

        expected = {
            "text": "legacy whisper api",
            "segments": [{"start": 0.0, "end": 1.0, "text": "legacy whisper api"}],
            "language": "en",
        }
        response = Mock()
        response.json.return_value = expected
        response.raise_for_status = Mock()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            create_tiny_wav(temp_audio.name)
            audio_path = temp_audio.name

        try:
            implementation = WhisperAsrApi(
                base_url="http://localhost:9000",
                provider="whisper",
                model="large-v3",
            )
            implementation.client.post = Mock(return_value=response)
            result = implementation.transcribe(
                audio=audio_path, options=build_options(vad_filter=True), language="en"
            )

            implementation.client.post.assert_called_once()
            call = implementation.client.post.call_args
            self.assertEqual("http://localhost:9000/asr", call.args[0])
            self.assertEqual("whisper", call.kwargs["params"]["provider"])
            self.assertEqual("large-v3", call.kwargs["params"]["model"])
            self.assertEqual("true", call.kwargs["params"]["vad_filter"])
            self.assertEqual(expected, result)
            self._assert_result_contract(result)
        finally:
            os.unlink(audio_path)

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
                implementation = WhisperAsrApi(base_url="http://localhost:5000")
                result = implementation.transcribe(
                    audio=audio_path,
                    options=build_options(vad_filter=False),
                    language="en",
                )

            kwargs = session.post.call_args.kwargs
            self.assertEqual(
                "http://localhost:5000/asr", session.post.call_args.args[0]
            )
            self.assertEqual("false", kwargs["params"]["vad_filter"])
            self.assertEqual("alpha bravo", kwargs["params"]["initial_prompt"])
            response.raise_for_status.assert_called_once()
            self.assertEqual(expected, result)
            self._assert_result_contract(result)
        finally:
            os.unlink(audio_path)


if __name__ == "__main__":
    unittest.main()

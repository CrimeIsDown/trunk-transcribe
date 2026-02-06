import importlib
import os
import sys
import tempfile
import types
import unittest
import wave
from collections import namedtuple
from types import SimpleNamespace
from unittest.mock import Mock, patch


def build_options(initial_prompt: str = "alpha bravo", vad_filter: bool = False) -> dict:
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


def import_module_with_stubs(module_name: str, stubs: dict[str, object]):
    previous_module = sys.modules.pop(module_name, None)
    try:
        with patch.dict(sys.modules, stubs):
            module = importlib.import_module(module_name)
    finally:
        if previous_module is not None:
            sys.modules[module_name] = previous_module
        else:
            sys.modules.pop(module_name, None)
    return module


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
                    implementation = DeepInfraApi(api_key="deepinfra-key", model="model-x")
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
                channels=[SimpleNamespace(alternatives=[SimpleNamespace(transcript="hello deepgram")])],
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

            self.assertEqual(
                {"options": "ok"}, transcribe_file_mock.call_args.args[1]
            )
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
                with patch(
                    "app.whisper.deepgram.PrerecordedOptions", return_value={}
                ):
                    implementation = DeepgramApi(api_key="deepgram-key", model="nova-2")
                    result = implementation.transcribe(
                        audio=audio_path, options=build_options(), language="en"
                    )

            self.assertEqual({"segments": [], "text": "", "language": "en"}, result)
            self._assert_result_contract(result)
        finally:
            os.unlink(audio_path)

    def test_whisper_transcribe_structural_contract(self):
        fake_whisper = types.ModuleType("whisper")
        fake_model = Mock()
        fake_model.transcribe.return_value = {
            "text": "hello whisper",
            "segments": [{"start": 0.0, "end": 0.5, "text": "hello whisper"}],
            "language": "en",
        }
        fake_whisper.load_model = Mock(return_value=fake_model)
        module = import_module_with_stubs("app.whisper.whisper", {"whisper": fake_whisper})

        implementation = module.Whisper("tiny")
        result = implementation.transcribe("audio.wav", build_options(), language="en")

        fake_whisper.load_model.assert_called_once_with("tiny")
        fake_model.transcribe.assert_called_once()
        kwargs = fake_model.transcribe.call_args.kwargs
        self.assertEqual("audio.wav", kwargs["audio"])
        self.assertEqual("en", kwargs["language"])
        self.assertEqual("alpha bravo", kwargs["initial_prompt"])
        self._assert_result_contract(result)

    def test_faster_whisper_transcribe_structural_contract(self):
        fake_faster_whisper = types.ModuleType("faster_whisper")
        segment_type = namedtuple("Segment", ["start", "end", "text"])

        class FakeWhisperModel:
            def __init__(self, *args, **kwargs):
                self.init_args = args
                self.init_kwargs = kwargs
                self.transcribe_kwargs = None

            def transcribe(self, **kwargs):
                self.transcribe_kwargs = kwargs
                return iter([segment_type(0.0, 0.5, "hello faster whisper")]), None

        fake_faster_whisper.WhisperModel = FakeWhisperModel
        module = import_module_with_stubs(
            "app.whisper.faster_whisper", {"faster_whisper": fake_faster_whisper}
        )

        with patch.dict(
            os.environ, {"TORCH_DEVICE": "cpu", "TORCH_DTYPE": "int8"}, clear=False
        ):
            implementation = module.FasterWhisper("tiny")
            result = implementation.transcribe(
                "audio.wav", build_options(vad_filter=True), language="en"
            )

        self.assertEqual("hello faster whisper", result["text"])
        self.assertEqual("en", result["language"])
        self.assertEqual(1, len(result["segments"]))
        self.assertEqual(
            "audio.wav", implementation.model.transcribe_kwargs["audio"]
        )
        self.assertTrue(implementation.model.transcribe_kwargs["vad_filter"])
        self._assert_result_contract(result)

    def test_whisper_s2t_transcribe_structural_contract(self):
        fake_whisper_s2t = types.ModuleType("whisper_s2t")
        fake_backends = types.ModuleType("whisper_s2t.backends")
        fake_ctranslate2 = types.ModuleType("whisper_s2t.backends.ctranslate2")
        fake_model_module = types.ModuleType("whisper_s2t.backends.ctranslate2.model")
        fake_model_module.BEST_ASR_CONFIG = {"beam_size": 1}

        class FakeS2TModel:
            def __init__(self):
                self.transcribe_called = False
                self.transcribe_with_vad_called = False

            def transcribe(self, *args, **kwargs):
                self.transcribe_called = True
                return [[{"start_time": 0.0, "end_time": 0.5, "text": "hello s2t"}]]

            def transcribe_with_vad(self, *args, **kwargs):
                self.transcribe_with_vad_called = True
                return [[{"start_time": 0.0, "end_time": 0.5, "text": "hello vad"}]]

        fake_model = FakeS2TModel()
        load_model_mock = Mock(return_value=fake_model)
        fake_whisper_s2t.load_model = load_model_mock

        module = import_module_with_stubs(
            "app.whisper.whisper_s2t",
            {
                "whisper_s2t": fake_whisper_s2t,
                "whisper_s2t.backends": fake_backends,
                "whisper_s2t.backends.ctranslate2": fake_ctranslate2,
                "whisper_s2t.backends.ctranslate2.model": fake_model_module,
            },
        )

        with patch.dict(
            os.environ, {"TORCH_DEVICE": "cpu", "TORCH_DTYPE": "int8"}, clear=False
        ):
            implementation = module.WhisperS2T("small")
            result = implementation.transcribe(
                "audio.wav", build_options(vad_filter=True), language="en"
            )

        self.assertTrue(fake_model.transcribe_with_vad_called)
        self.assertFalse(fake_model.transcribe_called)
        self.assertEqual("hello vad\n", result["text"])
        self.assertEqual("en", result["language"])
        self._assert_result_contract(result)
        self.assertEqual("small", load_model_mock.call_args.kwargs["model_identifier"])
        self.assertEqual("CTranslate2", load_model_mock.call_args.kwargs["backend"])

    def test_whisper_cpp_transcribe_structural_contract(self):
        from app.whisper.whisper_cpp import WhisperCpp

        with tempfile.TemporaryDirectory() as temp_dir:
            model_path = os.path.join(temp_dir, "ggml-tiny.bin")
            open(model_path, "wb").close()

            audio_path = os.path.join(temp_dir, "tiny.wav")
            create_tiny_wav(audio_path)

            csv_path = f"{audio_path}.csv"
            with open(csv_path, "w", encoding="utf-8") as csv_file:
                csv_file.write("start,end,text\n")
                csv_file.write("0,500,hello cpp\n")
                csv_file.write("500,1000,[SOUND]\n")
                csv_file.write("1000,1500,world cpp\n")

            completed_process = Mock()
            completed_process.check_returncode = Mock()
            with patch(
                "app.whisper.whisper_cpp.subprocess.run",
                return_value=completed_process,
            ) as run_mock:
                implementation = WhisperCpp("tiny", temp_dir)
                result = implementation.transcribe(
                    audio=audio_path,
                    options={
                        "initial_prompt": "alpha bravo",
                        "cleanup": False,
                        "vad_filter": False,
                        "decode_options": {"beam_size": 3, "best_of": 2},
                        "cleanup_config": [],
                    },
                    language="en",
                )

            args = run_mock.call_args.args[0]
            self.assertIn("--best-of", args)
            self.assertIn("2", args)
            self.assertIn("--beam-size", args)
            self.assertIn("3", args)
            self.assertIn("--prompt", args)
            self.assertEqual("hello cpp\nworld cpp", result["text"])
            self.assertEqual(2, len(result["segments"]))
            self.assertFalse(os.path.exists(csv_path))
            self._assert_result_contract(result)

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
            with patch("app.whisper.whisper_asr_api.requests.Session", return_value=session):
                implementation = WhisperAsrApi(base_url="http://localhost:5000")
                result = implementation.transcribe(
                    audio=audio_path,
                    options=build_options(vad_filter=False),
                    language="en",
                )

            kwargs = session.post.call_args.kwargs
            self.assertEqual("http://localhost:5000/asr", session.post.call_args.args[0])
            self.assertEqual("false", kwargs["params"]["vad_filter"])
            self.assertEqual("alpha bravo", kwargs["params"]["initial_prompt"])
            response.raise_for_status.assert_called_once()
            self.assertEqual(expected, result)
            self._assert_result_contract(result)
        finally:
            os.unlink(audio_path)


if __name__ == "__main__":
    unittest.main()

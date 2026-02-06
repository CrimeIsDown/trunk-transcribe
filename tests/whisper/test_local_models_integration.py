import os
import unittest

from app.whisper.task import WhisperTask


RUN_LOCAL_WHISPER_TESTS = os.getenv("RUN_LOCAL_WHISPER_TESTS", "").lower() == "true"
TINY_AUDIO_FILE = "tests/data/tiny.wav"


def build_options(vad_filter: bool = False) -> dict:
    return {
        "initial_prompt": "alpha bravo",
        "cleanup": False,
        "vad_filter": vad_filter,
        "decode_options": {"beam_size": 5},
        "cleanup_config": [],
    }


@unittest.skipUnless(
    RUN_LOCAL_WHISPER_TESTS, "Set RUN_LOCAL_WHISPER_TESTS=true to run local model tests"
)
class TestLocalWhisperImplementations(unittest.TestCase):
    def _assert_result_contract(self, result: dict):
        self.assertIn("text", result)
        self.assertIn("segments", result)
        self.assertIn("language", result)
        self.assertIsInstance(result["segments"], list)
        for segment in result["segments"]:
            self.assertIn("start", segment)
            self.assertIn("end", segment)
            self.assertIn("text", segment)

    def _run_implementation(self, implementation: str, model_name: str) -> None:
        task = WhisperTask()
        try:
            model = task.initialize_model(f"{implementation}:{model_name}")
        except ModuleNotFoundError as exc:
            self.skipTest(f"{implementation} dependency missing: {exc}")
        result = model.transcribe(TINY_AUDIO_FILE, build_options(vad_filter=False), "en")
        self._assert_result_contract(result)

    def test_whisper(self):
        model_name = os.getenv("LOCAL_WHISPER_MODEL", "tiny")
        self._run_implementation("whisper", model_name)

    def test_faster_whisper(self):
        model_name = os.getenv("LOCAL_FASTER_WHISPER_MODEL", "tiny")
        self._run_implementation("faster-whisper", model_name)

    def test_whispers2t(self):
        model_name = os.getenv("LOCAL_WHISPERS2T_MODEL", "tiny")
        self._run_implementation("whispers2t", model_name)

    @unittest.skipUnless(
        os.getenv("WHISPERCPP_MODEL_DIR"),
        "WHISPERCPP_MODEL_DIR must point to a directory with ggml model files",
    )
    def test_whisper_cpp(self):
        model_name = os.getenv("LOCAL_WHISPERCPP_MODEL", "tiny")
        self._run_implementation("whisper.cpp", model_name)


if __name__ == "__main__":
    unittest.main()

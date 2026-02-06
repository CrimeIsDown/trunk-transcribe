import os
import unittest

from app.whisper.deepgram import DeepgramApi
from app.whisper.deepinfra import DeepInfraApi
from app.whisper.openai import OpenAIApi


RUN_LIVE_PROVIDER_TESTS = os.getenv("RUN_LIVE_PROVIDER_TESTS", "").lower() == "true"
TINY_AUDIO_FILE = "tests/data/tiny.wav"


def build_options() -> dict:
    return {
        "initial_prompt": "alpha bravo",
        "cleanup": False,
        "vad_filter": False,
        "decode_options": {"beam_size": 5},
        "cleanup_config": [],
    }


@unittest.skipUnless(
    RUN_LIVE_PROVIDER_TESTS, "Set RUN_LIVE_PROVIDER_TESTS=true to run live provider tests"
)
class TestLiveProviders(unittest.TestCase):
    def _assert_result_contract(self, result: dict):
        self.assertIn("text", result)
        self.assertIn("segments", result)
        self.assertIn("language", result)
        self.assertIsInstance(result["segments"], list)
        for segment in result["segments"]:
            self.assertIn("start", segment)
            self.assertIn("end", segment)
            self.assertIn("text", segment)

    @unittest.skipUnless(os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY not set")
    def test_openai_live(self):
        implementation = OpenAIApi(api_key=os.environ["OPENAI_API_KEY"])
        result = implementation.transcribe(TINY_AUDIO_FILE, build_options(), "en")
        self._assert_result_contract(result)

    @unittest.skipUnless(os.getenv("DEEPGRAM_API_KEY"), "DEEPGRAM_API_KEY not set")
    def test_deepgram_live(self):
        implementation = DeepgramApi(api_key=os.environ["DEEPGRAM_API_KEY"], model="nova-2")
        result = implementation.transcribe(TINY_AUDIO_FILE, build_options(), "en")
        self._assert_result_contract(result)

    @unittest.skipUnless(os.getenv("DEEPINFRA_API_KEY"), "DEEPINFRA_API_KEY not set")
    def test_deepinfra_live(self):
        model = os.getenv("DEEPINFRA_MODEL", "openai/whisper-large-v3-turbo")
        implementation = DeepInfraApi(api_key=os.environ["DEEPINFRA_API_KEY"], model=model)
        result = implementation.transcribe(TINY_AUDIO_FILE, build_options(), "en")
        self._assert_result_contract(result)


if __name__ == "__main__":
    unittest.main()

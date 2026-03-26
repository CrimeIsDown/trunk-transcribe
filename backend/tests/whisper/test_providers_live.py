import os
import unittest

from app.whisper.whisper_asr_api import WhisperAsrApi


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
    RUN_LIVE_PROVIDER_TESTS,
    "Set RUN_LIVE_PROVIDER_TESTS=true to run live provider tests",
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
        implementation = WhisperAsrApi(
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model="whisper-1",
            provider="openai",
            headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        )
        result = implementation.transcribe(TINY_AUDIO_FILE, build_options(), "en")
        self._assert_result_contract(result)

    @unittest.skipUnless(os.getenv("DEEPINFRA_API_KEY"), "DEEPINFRA_API_KEY not set")
    def test_deepinfra_live(self):
        model = os.getenv("DEEPINFRA_MODEL", "openai/whisper-large-v3-turbo")
        implementation = WhisperAsrApi(
            base_url=os.getenv(
                "DEEPINFRA_BASE_URL", "https://api.deepinfra.com/v1/openai"
            ),
            model=model,
            provider="deepinfra",
            headers={"Authorization": f"Bearer {os.environ['DEEPINFRA_API_KEY']}"},
        )
        result = implementation.transcribe(TINY_AUDIO_FILE, build_options(), "en")
        self._assert_result_contract(result)


if __name__ == "__main__":
    unittest.main()

import os
import unittest
from time import sleep
from dotenv import load_dotenv

import requests

load_dotenv()


class TestEndToEnd(unittest.TestCase):
    def transcribe(self, call_audio_path: str, call_json_path: str) -> dict:
        API_BASE_URL = "http://127.0.0.1:8000"

        api_key = os.getenv("API_KEY", "")
        headers = {"Authorization": f"Bearer {api_key}"}

        with open(call_audio_path, "rb") as call_audio, open(
            call_json_path, "r"
        ) as call_json:
            r = requests.post(
                url=f"{API_BASE_URL}/tasks",
                params={"debug": True},
                files={"call_audio": call_audio, "call_json": call_json},
                timeout=5,
                headers=headers,
            )
        r.raise_for_status()
        result = r.json()
        pending_status = "PENDING"
        task_status = result.get("task_status", pending_status)
        task_id = result["task_id"]

        while task_status == pending_status:
            sleep(1)
            r = requests.get(
                url=f"{API_BASE_URL}/tasks/{task_id}", timeout=5, headers=headers
            )
            r.raise_for_status()
            result = r.json()
            task_status = result["task_status"]
        # Make sure we got the correct task while also throwing out something that would mess up our comparison alter
        self.assertEqual(task_id, result.pop("task_id"))
        return result

    def test_transcribes_digital(self):
        expected = {
            "task_result": "<i>E96:</i> some fake text",
            "task_status": "SUCCESS",
        }

        result = self.transcribe(
            "tests/data/1-1673118015_477787500-call_1.wav",
            "tests/data/1-1673118015_477787500-call_1.json",
        )

        self.assertDictEqual(expected, result)

    def test_transcribes_analog(self):
        expected = {
            "task_result": "some fake text",
            "task_status": "SUCCESS",
        }

        result = self.transcribe(
            "tests/data/11-1673118186_460378000-call_0.wav",
            "tests/data/11-1673118186_460378000-call_0.json",
        )

        self.assertDictEqual(expected, result)


if __name__ == "__main__":
    unittest.main()

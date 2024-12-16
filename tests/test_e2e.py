import json
import os
import unittest
from time import sleep

import requests
from dotenv import load_dotenv

from app.search.adapters import get_default_adapter
from app.search.helpers import get_default_index_name


load_dotenv()

original_s3_public_url = os.getenv("S3_PUBLIC_URL")

load_dotenv(".env.testing.local", override=True)

adapter = get_default_adapter()


class TestEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        index_name = get_default_index_name()
        adapter.delete_index(index_name)
        adapter.create_or_update_index(index_name)

    def transcribe(
        self,
        call_audio_path: str,
        call_json_path: str,
        endpoint: str = "calls",
        extra_params: dict = {},
    ) -> dict:
        api_base_url = os.getenv("API_BASE_URL")
        api_key = os.getenv("API_KEY")
        headers = {"Authorization": f"Bearer {api_key}"}

        with (
            open(call_audio_path, "rb") as call_audio,
            open(call_json_path, "r") as call_json,
        ):
            r = requests.post(
                url=f"{api_base_url}/{endpoint}",
                params=extra_params,
                files={"call_audio": call_audio, "call_json": call_json},
                timeout=5,
                headers=headers,
            )
        if r.status_code >= 300:
            try:
                print(r.json())
            except json.JSONDecodeError:
                print(r.text)
        r.raise_for_status()
        result = r.json()
        task_status = result.get("task_status", "PENDING")
        task_id = result["task_id"]

        tries = 0
        while task_status in ["PENDING", "RETRY"]:
            tries += 1
            self.assertLess(tries, 100, "Timed out waiting for task to complete")
            sleep(1)
            r = requests.get(
                url=f"{api_base_url}/tasks/{task_id}", timeout=5, headers=headers
            )
            r.raise_for_status()
            result = r.json()
            task_status = result["task_status"]
        # Make sure we got the correct task while also throwing out something that would mess up our comparison alter
        self.assertEqual(task_id, result.pop("task_id"))
        return result

    def test_transcribes_digital(self):
        result = self.transcribe(
            "tests/data/1-1673118015_477787500-call_1.wav",
            "tests/data/1-1673118015_477787500-call_1.json",
        )

        self.assertEqual("SUCCESS", result["task_status"])
        self.assertTrue("E96: " in result["task_result"])

        sleep(2)  # Wait for search to update

        result = adapter.search(
            get_default_index_name(), "96 central", {"filter_by": "units := E96"}
        )

        self.assertEqual(1, len(result["hits"]))

        hit = result["hits"][0]["document"]

        self.assertTrue('<i data-src="1410967">E96:</i> ' in hit["transcript"])

        self.assertTrue(isinstance(json.loads(hit["raw_metadata"]), dict))
        self.assertTrue(isinstance(json.loads(hit["raw_transcript"]), list))

        r = requests.get(
            hit["raw_audio_url"].replace(
                original_s3_public_url, os.getenv("S3_PUBLIC_URL")
            )
        )
        self.assertEqual(200, r.status_code)
        self.assertEqual("audio/mpeg", r.headers.get("content-type"))

    def test_transcribes_analog(self):
        result = self.transcribe(
            "tests/data/11-1673118186_460378000-call_0.wav",
            "tests/data/11-1673118186_460378000-call_0.json",
        )

        self.assertEqual("SUCCESS", result["task_status"])
        self.assertTrue(
            "2011" in result["task_result"] or "20-11" in result["task_result"]
        )
        self.assertTrue("\n" in result["task_result"])

        sleep(2)  # Wait for search to update

        result = adapter.search(
            get_default_index_name(),
            "2011",
            {"filter_by": "short_name := chi_cpd && audio_type := analog"},
        )

        self.assertEqual(1, len(result["hits"]))

        hit = result["hits"][0]["document"]

        self.assertTrue("<br>" in hit["transcript"] and "\n" not in hit["transcript"])

        self.assertTrue(isinstance(json.loads(hit["raw_metadata"]), dict))
        self.assertTrue(isinstance(json.loads(hit["raw_transcript"]), list))

        r = requests.get(
            hit["raw_audio_url"].replace(
                original_s3_public_url, os.getenv("S3_PUBLIC_URL")
            )
        )
        self.assertEqual(200, r.status_code)
        self.assertEqual("audio/mpeg", r.headers.get("content-type"))

    def test_transcribes_without_db(self):
        result = self.transcribe(
            "tests/data/9051-1699224861_773043750.0-call_20452.wav",
            "tests/data/9051-1699224861_773043750.0-call_20452.json",
            endpoint="tasks",
            extra_params={"whisper_implementation": "openai:whisper-1"},
        )

        self.assertEqual("SUCCESS", result["task_status"])
        self.assertTrue("1904399: " in result["task_result"])

        sleep(2)  # Wait for search to update

        result = adapter.search(
            get_default_index_name(),
            "additional information",
            {"filter_by": 'talkgroup_group := "ISP Troop 3 - Chicago"'},
        )

        self.assertEqual(1, len(result["hits"]))

        hit = result["hits"][0]["document"]

        self.assertTrue('<i data-src="1904399">1904399:</i> ' in hit["transcript"])

        self.assertTrue(isinstance(json.loads(hit["raw_metadata"]), dict))
        self.assertTrue(isinstance(json.loads(hit["raw_transcript"]), list))

        r = requests.get(
            hit["raw_audio_url"].replace(
                original_s3_public_url, os.getenv("S3_PUBLIC_URL")
            )
        )
        self.assertEqual(200, r.status_code)
        self.assertEqual("audio/mpeg", r.headers.get("content-type"))

    def test_transcribes_in_batch(self):
        if os.getenv("WHISPER_IMPLEMENTATION") != "whispers2t":
            self.skipTest("WHISPER_IMPLEMENTATION must be whispers2t to test")

        result = self.transcribe(
            "tests/data/9051-1699224861_773043750.0-call_20452.wav",
            "tests/data/9051-1699224861_773043750.0-call_20452.json",
            extra_params={"batch": "true"},
        )

        self.assertEqual("SUCCESS", result["task_status"])
        self.assertTrue("1904399: " in result["task_result"])

        sleep(2)  # Wait for search to update

        result = adapter.search(
            get_default_index_name(),
            "additional information",
            {"filter_by": 'talkgroup_group := "ISP Troop 3 - Chicago"'},
        )

        self.assertEqual(1, len(result["hits"]))

        hit = result["hits"][0]["document"]

        self.assertTrue('<i data-src="1904399">1904399:</i> ' in hit["transcript"])

        self.assertTrue(isinstance(json.loads(hit["raw_metadata"]), dict))
        self.assertTrue(isinstance(json.loads(hit["raw_transcript"]), list))

        r = requests.get(
            hit["raw_audio_url"].replace(
                original_s3_public_url, os.getenv("S3_PUBLIC_URL")
            )
        )
        self.assertEqual(200, r.status_code)
        self.assertEqual("audio/mpeg", r.headers.get("content-type"))


if __name__ == "__main__":
    unittest.main()

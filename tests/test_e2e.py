import json
import os
import unittest
from time import sleep

import requests
from dotenv import load_dotenv

from app import search

load_dotenv()


class TestEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        index = search.get_index(search.get_default_index_name())
        index.delete()

        show_success = False
        while True:
            try:
                requests.get(url=str(os.getenv("API_BASE_URL")), timeout=5)
                if show_success:
                    print("Connected to API successfully.")
                break
            except:
                print("Waiting for API to come online...")
                show_success = True
                sleep(1)

    def transcribe(self, call_audio_path: str, call_json_path: str) -> dict:
        api_base_url = os.getenv("API_BASE_URL")
        api_key = os.getenv("API_KEY")
        headers = {"Authorization": f"Bearer {api_key}"}

        with open(call_audio_path, "rb") as call_audio, open(
            call_json_path, "r"
        ) as call_json:
            r = requests.post(
                url=f"{api_base_url}/tasks",
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
                url=f"{api_base_url}/tasks/{task_id}", timeout=5, headers=headers
            )
            r.raise_for_status()
            result = r.json()
            task_status = result["task_status"]
        # Make sure we got the correct task while also throwing out something that would mess up our comparison alter
        self.assertEqual(task_id, result.pop("task_id"))
        return result

    def search(self, query: str, options):
        index = search.get_index(search.get_default_index_name())
        return index.search(query, opt_params=options)

    def test_transcribes_digital(self):
        result = self.transcribe(
            "tests/data/1-1673118015_477787500-call_1.wav",
            "tests/data/1-1673118015_477787500-call_1.json",
        )

        self.assertEqual("SUCCESS", result["task_status"])
        self.assertTrue("E96: " in result["task_result"])

        result = self.search("96 central", {"filter": ["units = E96"]})

        self.assertEqual(1, len(result["hits"]))
        self.assertTrue(
            '<i data-src="1410967">E96:</i> ' in result["hits"][0]["transcript"]
        )

        self.assertTrue(isinstance(json.loads(result["hits"][0]["raw_metadata"]), dict))
        self.assertTrue(
            isinstance(json.loads(result["hits"][0]["raw_transcript"]), list)
        )

        r = requests.get(result["hits"][0]["raw_audio_url"])
        self.assertEqual(200, r.status_code)

    def test_transcribes_analog(self):
        result = self.transcribe(
            "tests/data/11-1673118186_460378000-call_0.wav",
            "tests/data/11-1673118186_460378000-call_0.json",
        )

        self.assertEqual("SUCCESS", result["task_status"])
        self.assertTrue("2011" in result["task_result"])
        self.assertTrue("\n" in result["task_result"])

        result = self.search(
            "2011", {"filter": ["short_name = chi_cpd", "audio_type = analog"]}
        )

        self.assertEqual(1, len(result["hits"]))
        self.assertTrue(
            "<br>" in result["hits"][0]["transcript"]
            and "\n" not in result["hits"][0]["transcript"]
        )

        self.assertTrue(isinstance(json.loads(result["hits"][0]["raw_metadata"]), dict))
        self.assertTrue(
            isinstance(json.loads(result["hits"][0]["raw_transcript"]), list)
        )

        r = requests.get(result["hits"][0]["raw_audio_url"])
        self.assertEqual(200, r.status_code)
        self.assertEqual("audio/mpeg", r.headers.get("content-type"))


if __name__ == "__main__":
    unittest.main()

import logging
import os
import unittest
from time import sleep

import requests
from dotenv import load_dotenv

from app.notifications import notification

load_dotenv()


class TestNotification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        while True:
            try:
                requests.get(
                    url=f"{os.getenv('API_BASE_URL')}/config/notifications.json",
                    headers={"Authorization": f"Bearer {os.getenv('API_KEY')}"},
                    timeout=5,
                ).raise_for_status()
                logging.info("Connected to API successfully.")
                break
            except Exception as e:
                logging.error(e)
                logging.info("Waiting for API to come online...")
                sleep(1)

    def test_alerts_when_keyword_and_traveltime_match(self):
        config = {
            "channels": [
                "tgram://$TELEGRAM_BOT_TOKEN/-1",
            ],
            "keywords": ["96"],
            "location": {
                "geo": {"lat": 41.872321, "lng": -87.764948},
                "travel_time": 1800,
            },
        }
        transcript = "E96: Engine company 96 in the truck 333 north central"
        geo = {
            "geo": {"lat": 41.886719, "lng": -87.764503},
            "geo_formatted_address": "333 N Central Ave, Chicago, IL 60644",
        }

        should_send, title, body = notification.should_send_alert(config, transcript, geo)  # type: ignore

        self.assertTrue(should_send)
        self.assertRegex(
            title,
            r"96 detected in transcript Location 333 N Central Ave, Chicago, IL 60644 \(under ([0-9]+) minutes away\) detected in transcript",
        )
        self.assertEqual(transcript, body)

    def test_does_not_alert_when_keyword_and_traveltime_do_not_match(self):
        config = {
            "channels": [
                "tgram://$TELEGRAM_BOT_TOKEN/-1",
            ],
            "keywords": ["abc"],
            "location": {
                "geo": {"lat": 41.872321, "lng": -87.764948},
                "travel_time": 60,
            },
        }
        transcript = "E96: Engine company 96 in the truck 333 north central"
        geo = {
            "geo": {"lat": 41.886719, "lng": -87.764503},
            "geo_formatted_address": "333 N Central Ave, Chicago, IL 60644",
        }

        should_send, title, body = notification.should_send_alert(config, transcript, geo)  # type: ignore

        self.assertFalse(should_send)
        self.assertEqual(title, "")
        self.assertEqual(body, transcript)

    def test_does_not_alert_when_keyword_does_not_match(self):
        config = {
            "channels": [
                "tgram://$TELEGRAM_BOT_TOKEN/-1",
            ],
            "keywords": ["abc"],
        }
        transcript = "E96: Engine company 96 in the truck 333 north central"
        geo = {
            "geo": {"lat": 41.886719, "lng": -87.764503},
            "geo_formatted_address": "333 N Central Ave, Chicago, IL 60644",
        }

        should_send, title, body = notification.should_send_alert(config, transcript, geo)  # type: ignore

        self.assertFalse(should_send)
        self.assertEqual(title, "")
        self.assertEqual(body, transcript)

    def test_does_not_alert_when_no_location(self):
        config = {
            "channels": [
                "tgram://$TELEGRAM_BOT_TOKEN/-1",
            ],
            "location": {
                "geo": {"lat": 41.872321, "lng": -87.764948},
                "travel_time": 1,
            },
        }
        transcript = "blah"
        geo = None

        should_send, title, body = notification.should_send_alert(config, transcript, geo)  # type: ignore

        self.assertFalse(should_send)
        self.assertEqual(title, "")
        self.assertEqual(body, transcript)


if __name__ == "__main__":
    unittest.main()

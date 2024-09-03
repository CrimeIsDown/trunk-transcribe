import logging
import os
import unittest
from time import sleep

import requests
from dotenv import load_dotenv
from geopy.point import Point

from app.geocoding import routing

load_dotenv()


class TestRouting(unittest.TestCase):
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
        logging.getLogger().setLevel(logging.DEBUG)

    def test_calculates_route_directions(self):
        origin = Point(latitude=41.8303654, longitude=-87.6239086)
        destination = Point(latitude=41.8867315, longitude=-87.7644538)

        duration = routing.calculate_route_duration_via_directions(
            origin, destination
        )

        self.assertLess(duration, 3600)

    def test_calculates_route_isochrone(self):
        origin = Point(latitude=41.8303654, longitude=-87.6239086)
        destination = Point(latitude=41.8867315, longitude=-87.7644538)
        threshold = 30 * 60

        duration = routing.calculate_route_duration_via_isochrone(
            origin, destination, threshold
        )

        self.assertLess(duration, threshold * 60)


if __name__ == "__main__":
    unittest.main()

import logging
import os
import unittest
from time import sleep

import requests
from dotenv import load_dotenv
from geopy.point import Point

from app import geocoding
from app.metadata import Metadata
from app.transcript import Transcript

load_dotenv(".env.testing")
load_dotenv()


class TestGeocoding(unittest.TestCase):
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

    def test_lookup_geo(self):
        metadata = Metadata(
            {
                "short_name": "chi_cfd",
                "talkgroup_description": "Fire North",
                "talkgroup_group": "Chicago Fire Department",
            }
        )
        transcript = Transcript(
            [
                (None, "Take the fire at 333 north central."),
            ]
        )

        result = geocoding.lookup_geo(metadata, transcript, geocoder="arcgis")

        self.assertIsNotNone(result)

        self.assertEqual(
            result["geo_formatted_address"],
            "333 N Central Ave, Chicago, Illinois, 60644",
        )

    def test_geocodes_valid_address_geocodio(self):
        address_parts = {
            "address": "333 north central",
            "city": "Chicago",
            "state": "IL",
            "country": "US",
        }
        expected_result = {
            "geo": {"lat": 41.886719, "lng": -87.764503},
            "geo_formatted_address": "333 N Central Ave, Chicago, IL 60644",
        }

        result = geocoding.geocode(address_parts, geocoder="geocodio")

        self.assertDictEqual(expected_result, result)

    def test_geocodes_valid_address_google(self):
        address_parts = {
            "address": "333 north central ave",
            "city": "Chicago",
            "state": "IL",
            "country": "US",
        }
        expected_result = {
            "geo": {"lat": 41.8867315, "lng": -87.7644538},
            "geo_formatted_address": "333 N Central Ave, Chicago, IL 60644, USA",
        }

        result = geocoding.geocode(address_parts, geocoder="googlev3")

        self.assertDictEqual(expected_result, result)

    def test_calculates_route(self):
        origin = Point(latitude=41.8303654, longitude=-87.6239086)
        destination = Point(latitude=41.8867315, longitude=-87.7644538)

        duration = geocoding.calculate_route_duration(origin, destination)

        self.assertLess(duration, 3600)


if __name__ == "__main__":
    unittest.main()

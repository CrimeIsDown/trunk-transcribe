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
        logging.getLogger().setLevel(logging.DEBUG)

    def test_lookup_geo_with_llm(self):
        if not os.getenv("PELIAS_DOMAIN"):
            self.skipTest("PELIAS_DOMAIN not set")

        transmissions = [
            (
                Metadata(
                    {
                        "short_name": "sc21102",
                        "talkgroup_description": "3 East: Elmhurst, Oakbrook Terrace Police",
                        "talkgroup_group": "DuPage County - DuPage Public Safety Communications (DU-COMM)",
                    }  # type: ignore
                ),
                Transcript(
                    [
                        (
                            None,
                            "Oakbrook Care is here to advise your FDs enroute to 1 Tower Lane for a fire alarm.",
                        ),
                    ]
                ),
                "1 Tower Lane, Oakbrook Terrace, IL, USA",
                "pelias",
            ),
            (
                Metadata(
                    {
                        "short_name": "chisuburbs",
                        "talkgroup_description": "Fire Dispatch: South",
                        "talkgroup_group": "Regional Emergency Dispatch - RED Center (Northbrook)",
                    }  # type: ignore
                ),
                Transcript(
                    [
                        (
                            {
                                "pos": 0,
                                "src": 1,
                                "tag": "",
                                "time": 1714540304,
                                "emergency": 0,
                                "signal_system": "",
                                "transcript_prompt": "",
                            },
                            "Ambulance 62, side patient, Rivers Casino, 3000, South Des Plaines River Road, in Des Plaines, grid 6284, 3000, South Des Plaines River Road, side patient, Ambulance 62.",
                        ),
                    ]
                ),
                "3000 South Des Plaines River Road, Rosemont, IL, USA",
                "pelias",
            ),
        ]

        for metadata, transcript, address, geocoder in transmissions:
            result = geocoding.lookup_geo(metadata, transcript, geocoder)

            self.assertIsNotNone(result, f"Expected to get {address} but got None")

            if result:
                self.assertEqual(
                    result["geo_formatted_address"],
                    address,
                )

    def test_geocodes_valid_address_geocodio(self):
        address_parts = {
            "address": "Clinton and Jackson",
            "city": "Chicago",
            "state": "IL",
            "country": "US",
        }
        expected_result = {
            "geo": {"lat": 41.878026, "lng": -87.641069},
            "geo_formatted_address": "S Clinton St and W Jackson Blvd, Chicago, IL 60661",
        }

        result = geocoding.geocode(address_parts, geocoder="geocodio")

        self.assertIsNotNone(result)
        if result:
            self.assertEqual(
                expected_result["geo_formatted_address"],
                result["geo_formatted_address"],
            )
            self.assertAlmostEqual(
                expected_result["geo"]["lat"], result["geo"]["lat"], places=4
            )
            self.assertAlmostEqual(
                expected_result["geo"]["lng"], result["geo"]["lng"], places=4
            )

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

        self.assertIsNotNone(result)
        if result:
            self.assertEqual(
                expected_result["geo_formatted_address"],
                result["geo_formatted_address"],
            )
            self.assertAlmostEqual(
                expected_result["geo"]["lat"], result["geo"]["lat"], places=4
            )
            self.assertAlmostEqual(
                expected_result["geo"]["lng"], result["geo"]["lng"], places=4
            )

    def test_geocodes_valid_address_arcgis(self):
        address_parts = {
            "address": "333 north central ave",
            "city": "Chicago",
            "state": "IL",
            "country": "US",
        }
        expected_result = {
            "geo": {"lat": 41.8867315, "lng": -87.764651},
            "geo_formatted_address": "333 N Central Ave, Chicago, Illinois, 60644",
        }

        result = geocoding.geocode(address_parts, geocoder="arcgis")

        self.assertIsNotNone(result)
        if result:
            self.assertEqual(
                expected_result["geo_formatted_address"],
                result["geo_formatted_address"],
            )
            self.assertAlmostEqual(
                expected_result["geo"]["lat"], result["geo"]["lat"], places=4
            )
            self.assertAlmostEqual(
                expected_result["geo"]["lng"], result["geo"]["lng"], places=4
            )

    def test_geocodes_valid_address_mapbox(self):
        address_parts = {
            "address": "333 north central ave",
            "city": "Chicago",
            "state": "IL",
            "country": "US",
        }
        expected_result = {
            "geo": {"lat": 41.886711, "lng": -87.76451},
            "geo_formatted_address": "333 North Central Avenue, Chicago, Illinois 60644, United States",
        }

        result = geocoding.geocode(address_parts, geocoder="mapbox")

        self.assertIsNotNone(result)
        if result:
            self.assertEqual(
                expected_result["geo_formatted_address"],
                result["geo_formatted_address"],
            )
            self.assertAlmostEqual(
                expected_result["geo"]["lat"], result["geo"]["lat"], places=4
            )
            self.assertAlmostEqual(
                expected_result["geo"]["lng"], result["geo"]["lng"], places=4
            )

    def test_calculates_route_directions(self):
        origin = Point(latitude=41.8303654, longitude=-87.6239086)
        destination = Point(latitude=41.8867315, longitude=-87.7644538)

        duration = geocoding.calculate_route_duration_via_directions(
            origin, destination
        )

        self.assertLess(duration, 3600)

    def test_calculates_route_isochrone(self):
        origin = Point(latitude=41.8303654, longitude=-87.6239086)
        destination = Point(latitude=41.8867315, longitude=-87.7644538)
        threshold = 30 * 60

        duration = geocoding.calculate_route_duration_via_isochrone(
            origin, destination, threshold
        )

        self.assertLess(duration, threshold * 60)


if __name__ == "__main__":
    unittest.main()

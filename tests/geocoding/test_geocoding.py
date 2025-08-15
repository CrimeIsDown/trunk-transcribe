import os
import unittest

from app.geocoding import geocoding
from app.models.metadata import Metadata
from app.models.transcript import Transcript


class TestGeocoding(unittest.TestCase):
    def test_lookup_geo_with_llm(self):
        if not os.getenv("PELIAS_DOMAIN"):
            self.skipTest("PELIAS_DOMAIN not set")

        geocoding_service_original = os.getenv("GEOCODING_SERVICE")
        os.environ["GEOCODING_SERVICE"] = "geocodio,pelias"
        geocoder = None

        transmissions = [
            (
                Metadata(
                    {
                        "short_name": "sc21102",
                        "talkgroup_description": "3 East: Elmhurst, Oakbrook Terrace Police",
                        "talkgroup_group": "DuPage County - DuPage Public Safety Communications (DU-COMM)",
                    }
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
                geocoder,
            ),
            (
                Metadata(
                    {
                        "short_name": "chisuburbs",
                        "talkgroup_description": "Fire Dispatch: South",
                        "talkgroup_group": "Regional Emergency Dispatch - RED Center (Northbrook)",
                    }
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
                "3000 S Des Plaines River Rd, Des Plaines, IL 60018",
                geocoder,
            ),
            (
                Metadata(
                    {
                        "short_name": "chi_oemc",
                        "talkgroup_description": "Fire Supression North",
                        "talkgroup_group": "Chicago Fire Department",
                    }
                ),
                Transcript(
                    [
                        (
                            {
                                "pos": 0,
                                "src": 0,
                                "tag": "",
                                "time": 1714540304,
                                "emergency": 0,
                                "signal_system": "",
                                "transcript_prompt": "",
                            },
                            "All right, 98 into 98. It looks like that this place is located inside of the Jane Addams Memorial Park. Must be a cafe inside of there.",
                        ),
                    ]
                ),
                None,
                "pelias",
            ),
            (
                Metadata(
                    {
                        "short_name": "chi_cpd",
                        "talkgroup_description": "Citywide 1",
                        "talkgroup_group": "Chicago Police Department",
                    }
                ),
                Transcript(
                    [
                        (
                            {
                                "pos": 0,
                                "src": 0,
                                "tag": "",
                                "time": 1714540304,
                                "emergency": 0,
                                "signal_system": "",
                                "transcript_prompt": "",
                            },
                            "20 minutes to 8 on Citywide. Assault in progress. 6-1 in Westman at the laundromat. Male Hispanic staring at her daughter and standing in front of her child, also being told to leave. Offender's got a red shirt, pink pants. That's a threat on that.",
                        ),
                    ]
                ),
                None,
                "pelias",
            ),
        ]

        for metadata, transcript, address, geocoder in transmissions:
            result = geocoding.lookup_geo(metadata, transcript, geocoder)

            if address:
                self.assertIsNotNone(result, f"Expected to get {address} but got None")
            else:
                self.assertIsNone(
                    result,
                    f"Expected to get None but got {result['geo_formatted_address'] if result else ''}",
                )

            if result:
                self.assertEqual(
                    address,
                    result["geo_formatted_address"],
                )

        os.environ["GEOCODING_SERVICE"] = geocoding_service_original or ""

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
                expected_result["geo"]["lat"], result["geo"]["lat"], places=3
            )
            self.assertAlmostEqual(
                expected_result["geo"]["lng"], result["geo"]["lng"], places=3
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
                expected_result["geo"]["lat"], result["geo"]["lat"], places=3
            )
            self.assertAlmostEqual(
                expected_result["geo"]["lng"], result["geo"]["lng"], places=3
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
            "geo_formatted_address": "333 North Central Avenue, Chicago, Illinois, 60644",
        }

        result = geocoding.geocode(address_parts, geocoder="arcgis")

        self.assertIsNotNone(result)
        if result:
            self.assertEqual(
                expected_result["geo_formatted_address"],
                result["geo_formatted_address"],
            )
            self.assertAlmostEqual(
                expected_result["geo"]["lat"], result["geo"]["lat"], places=3
            )
            self.assertAlmostEqual(
                expected_result["geo"]["lng"], result["geo"]["lng"], places=3
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
                expected_result["geo"]["lat"], result["geo"]["lat"], places=3
            )
            self.assertAlmostEqual(
                expected_result["geo"]["lng"], result["geo"]["lng"], places=3
            )


if __name__ == "__main__":
    unittest.main()

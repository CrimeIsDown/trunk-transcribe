import unittest

from geopy.point import Point

from app.geocoding import routing


class TestRouting(unittest.TestCase):
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

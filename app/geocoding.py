import logging
import re
import os
import sys
from typing import Tuple, TypedDict

import sentry_sdk
from geopy.point import Point
from geopy.exc import GeocoderQueryError
from geopy.geocoders import get_geocoder_for_service
from google.api_core.client_options import ClientOptions
from google.maps import routing_v2

from .metadata import Metadata
from .transcript import Transcript
from . import llm


class Geo(TypedDict):
    lat: float
    lng: float


class GeoResponse(TypedDict):
    geo: Geo
    geo_formatted_address: str


def build_address_regex(include_intersections: bool = True):
    street_name = r"((?:[A-Z]\w+|[0-9]+(?:st|th|rd|nd))(?: [A-Z]\w+)?)"
    street_number = r"([0-9.,-]+)"
    direction = r"(?:block of )?(North|West|East|South)?(?: ?on)?"
    address = rf"{street_number} {direction} {street_name}"
    intersection = rf"{street_name} (?:and|in) {street_name}"
    regex = rf"({intersection}|{address})" if include_intersections else rf"({address})"
    return regex


ADDRESS_REGEX = build_address_regex(
    os.getenv("GEOCODING_INCLUDE_INTERSECTIONS", "true") == "true"
)


# TODO: write tests
def extract_address(transcript: str, ignore_case: bool = False) -> str | None:
    match = re.search(ADDRESS_REGEX, transcript, re.IGNORECASE if ignore_case else 0)
    if match:
        if match.group(1) and match.group(2):
            return f"{match.group(2)} and {match.group(3)}"
        return re.sub(
            r"[-.,]",
            "",
            f"{match.group(4)}{' ' + match.group(5) if match.group(5) else ''} {match.group(6)}",
        )

    return None


def geocode(
    address_parts: dict, geocoder: str | None = None
) -> GeoResponse | None:  # pragma: no cover
    if geocoder == "geocodio" or (os.getenv("GEOCODIO_API_KEY") and geocoder is None):
        geocoder = "geocodio"
        config = {"api_key": os.getenv("GEOCODIO_API_KEY")}
        query = {
            "query": {
                "street": address_parts["address"],
                "city": address_parts["city"],
                "state": address_parts["state"],
                "country": address_parts["country"],
            }
        }
    elif geocoder == "googlev3" or (
        os.getenv("GOOGLE_MAPS_API_KEY") and geocoder is None
    ):
        geocoder = "googlev3"
        config = {"api_key": os.getenv("GOOGLE_MAPS_API_KEY")}
        query = {
            "query": address_parts["address"],
            "components": {
                "locality": address_parts["city"],
                "administrative_area_level_1": address_parts["state"],
                "country": address_parts["country"],
            },
            "bounds": address_parts.get("bounds"),
        }
    elif geocoder == "arcgis" or (
        os.getenv("ARCGIS_USERNAME")
        and os.getenv("ARCGIS_PASSWORD")
        and geocoder is None
    ):
        geocoder = "arcgis"
        config = {
            "username": os.getenv("ARCGIS_USERNAME"),
            "password": os.getenv("ARCGIS_PASSWORD"),
            "referer": os.getenv("API_BASE_URL"),
        }
        query = {
            "query": f"{address_parts['address']}, {address_parts['city']}, {address_parts['state']}, {address_parts['country']}"
        }
    else:
        raise RuntimeError("Unsupported geocoder or no geocoding envs defined")

    cls = get_geocoder_for_service(geocoder)
    geolocator = cls(**config)
    try:
        location = geolocator.geocode(**query)
    except GeocoderQueryError:
        # Probably got "Could not geocode address. No matches found."
        return None

    if not location:
        return None

    if geocoder == "geocodio":
        if location.raw.get("accuracy_type", []) in [
            "street_center",
            "place",
            "county",
            "state",
        ]:
            return None
    elif geocoder == "googlev3":
        if location.raw["geometry"]["location_type"] in [
            "APPROXIMATE",
            "GEOMETRIC_CENTER",
        ]:
            return None

    return {
        "geo": {
            "lat": location.latitude,
            "lng": location.longitude,
        },
        "geo_formatted_address": location.address,
    }


def lookup_geo(
    metadata: Metadata, transcript: Transcript, geocoder: str | None = None
) -> GeoResponse | None:
    if metadata["short_name"] in filter(
        lambda name: len(name), os.getenv("GEOCODING_ENABLED_SYSTEMS", "").split(",")
    ):
        default_address_parts = {
            "city": os.getenv("GEOCODING_CITY"),
            "state": os.getenv("GEOCODING_STATE"),
            "country": os.getenv("GEOCODING_COUNTRY", "US"),
        }
        bounds_raw = os.getenv("GOOGLE_GEOCODING_BOUNDS")
        if bounds_raw:
            default_address_parts["bounds"] = [
                Point(bound) for bound in bounds_raw.split("|")
            ]
        else:
            default_address_parts["bounds"] = None

        llm_model = llm.create_model()

        for segment in transcript.transcript:
            address_parts = default_address_parts.copy()
            address_parts["address"] = extract_address(segment[1])

            if llm_model and not address_parts["address"]:
                result = llm.extract_address(llm_model, segment[1], metadata)
                if result:
                    address_parts.update(result)

            if address_parts["address"]:
                try:
                    return geocode(address_parts, geocoder=geocoder)
                except Exception as e:
                    sentry_sdk.capture_exception(e)
                    logging.error(
                        f"Got exception while geocoding: {repr(e)}", exc_info=e
                    )


def calculate_route_duration(origin: Point, destination: Point) -> int:
    # Create a client
    options = ClientOptions(api_key=os.getenv("GOOGLE_MAPS_API_KEY"))
    client = routing_v2.RoutesClient(client_options=options)

    # Initialize request argument(s)
    request = routing_v2.ComputeRoutesRequest(
        origin=routing_v2.Waypoint(
            location=routing_v2.Location(
                lat_lng={"latitude": origin.latitude, "longitude": origin.longitude}
            )
        ),
        destination=routing_v2.Waypoint(
            location=routing_v2.Location(
                lat_lng={
                    "latitude": destination.latitude,
                    "longitude": destination.longitude,
                }
            )
        ),
        travel_mode=routing_v2.RouteTravelMode.DRIVE,
        routing_preference=routing_v2.RoutingPreference.TRAFFIC_AWARE,
    )

    # Make the request
    response = client.compute_routes(
        request=request, metadata=[("x-goog-fieldmask", "routes.duration")]
    )

    if len(response.routes):
        return response.routes[0].duration.seconds

    # If there are no routes, give the maximum possible time - this simplifies logic using this method
    return sys.maxsize

import logging
import re
import os
import sys
from typing_extensions import TypedDict

import requests
import sentry_sdk
from geopy.location import Location
from geopy.point import Point
from geopy.exc import GeocoderQueryError
from geopy.geocoders import get_geocoder_for_service

from .exceptions import GeocodingException
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
    elif geocoder == "mapbox" or (os.getenv("MAPBOX_API_KEY") and geocoder is None):
        geocoder = "mapbox"
        config = {"api_key": os.getenv("MAPBOX_API_KEY")}
        query = {
            "query": f"{address_parts['address']}, {address_parts['city']}, {address_parts['state']}",
            "country": address_parts["country"],
            "bbox": address_parts.get("bounds"),
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
        raise GeocodingException("Unsupported geocoder or no geocoding envs defined")

    cls = get_geocoder_for_service(geocoder)
    geolocator = cls(**config)
    try:
        locations: list[Location] = geolocator.geocode(exactly_one=False, **query)
    except GeocoderQueryError:
        # Probably got "Could not geocode address. No matches found."
        return None

    if not locations:
        return None

    def is_location_valid(location: Location) -> bool:
        if geocoder == "geocodio":
            if location.raw.get("accuracy_type", []) in [
                "street_center",
                "place",
                "county",
                "state",
            ]:
                return False
        elif geocoder == "mapbox":
            if "address" not in location.raw["place_type"]:
                return False
        elif geocoder == "googlev3":
            if location.raw["geometry"]["location_type"] in [
                "APPROXIMATE",
                "GEOMETRIC_CENTER",
            ]:
                return False
        elif geocoder == "arcgis":
            if location.raw["score"] < 50:
                return False

        if address_parts["city"] not in location.address:
            return False
        # TODO: check state as well

        return True

    possible_locations = filter(is_location_valid, locations)
    # This assumes the locations are sorted by most accurate first
    location = next(possible_locations, None)

    if location:
        return {
            "geo": {
                "lat": location.latitude,
                "lng": location.longitude,
            },
            "geo_formatted_address": location.address,
        }

    return None


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
        bounds_raw = os.getenv("GEOCODING_BOUNDS")
        if bounds_raw:
            default_address_parts["bounds"] = [
                Point(bound) for bound in bounds_raw.split("|")
            ]
        else:
            default_address_parts["bounds"] = None

        llm_model = llm.create_model()

        transcript_txt = transcript.txt_nosrc

        address_parts = default_address_parts.copy()
        address_parts["address"] = extract_address(transcript_txt)

        # If we did not find the address through our regex, then we use the LLM model to extract it as long as the transcript contains a number (possibly indicating an address)
        if (
            llm_model
            and not address_parts["address"]
            and re.search(r"[0-9]", transcript_txt)
            and len(transcript_txt) > 20
        ):
            result = llm.extract_address(llm_model, transcript_txt, metadata)
            if result:
                address_parts.update(result)

        if address_parts["address"]:
            try:
                return geocode(address_parts, geocoder=geocoder)
            except Exception as e:
                sentry_sdk.capture_exception(e)
                logging.error(f"Got exception while geocoding: {repr(e)}", exc_info=e)


def calculate_route_duration(origin: Point, destination: Point) -> int:
    profile = "mapbox/driving-traffic"
    coordinates = f"{origin.longitude},{origin.latitude};{destination.longitude},{destination.latitude}"
    url = f"https://api.mapbox.com/directions/v5/{profile}/{coordinates}"

    response = requests.get(
        url,
        params={
            "access_token": os.getenv("MAPBOX_API_KEY"),
            "overview": "false",
        },
    )
    response.raise_for_status()
    mapbox_response = response.json()

    if len(mapbox_response["routes"]):
        return mapbox_response["routes"][0]["duration"]

    # If there are no routes, give the maximum possible time - this simplifies logic using this method
    return sys.maxsize

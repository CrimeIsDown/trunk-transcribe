from datetime import timedelta
import logging
import re
import os
import sys
from typing import Any
from typing_extensions import TypedDict

import requests
from requests_cache import CachedSession
import sentry_sdk
from shapely.geometry import shape, Point as ShapePoint
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


def contains_address(transcript: str):
    street_suffixes = [
        "street",
        "avenue",
        "road",
        "drive",
        "court",
        "boulevard",
        "circle",
        "lane",
        "way",
        "place",
        "terrace",
        "parkway",
        "highway",
        "expressway",
        "trail",
        "loop",
        "crescent",
        "path",
        "plaza",
        "square",
        "alley",
        "drive",
        "park",
        "turnpike",
        "pike",
        "route",
    ]
    cardinal_directions = ["north", "south", "east", "west"]
    return (
        bool(re.search(ADDRESS_REGEX, transcript, re.IGNORECASE))
        or any(suffix in transcript.lower() for suffix in street_suffixes)
        or any(direction in transcript.lower() for direction in cardinal_directions)
        or ("block of" in transcript.lower())
        or ("intersection" in transcript.lower())
    )


def geocode(
    address_parts: dict, geocoder: str | None = None
) -> GeoResponse | None:  # pragma: no cover
    query = {
        "query": f"{address_parts['address']}, {address_parts['city']}, {address_parts['state']}, {address_parts['country']}"
    }
    if not geocoder:
        geocoder = os.getenv("GEOCODING_SERVICE")

    if geocoder == "geocodio" or (os.getenv("GEOCODIO_API_KEY") and geocoder is None):
        geocoder = "geocodio"
        config = {"api_key": os.getenv("GEOCODIO_API_KEY")}
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
    elif geocoder == "nominatim":
        geocoder = "nominatim"
        config = {
            "timeout": 10,
            "user_agent": "trunk-transcribe v0 (https://github.com/CrimeIsDown/trunk-transcribe)",
        }
    elif geocoder == "pelias":
        geocoder = "pelias"
        config: dict[str, Any] = {
            "domain": os.getenv("PELIAS_DOMAIN"),
            "scheme": os.getenv("PELIAS_SCHEME", "https"),
            "timeout": 10,
        }
        if os.getenv("PELIAS_API_KEY"):
            config["api_key"] = os.getenv("PELIAS_API_KEY")
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
        # import json
        # logging.debug(json.dumps(location.raw, indent=2))
        is_accurate = True
        if geocoder == "geocodio" and (
            location.raw.get("accuracy_type", [])
            in [
                "street_center",
                "place",
                "county",
                "state",
            ]
            or location.raw.get("accuracy", 0) < 0.5
        ):
            is_accurate = False
        elif geocoder == "mapbox" and "address" not in location.raw["place_type"]:
            is_accurate = False
        elif geocoder == "googlev3" and location.raw["geometry"]["location_type"] in [
            "APPROXIMATE",
            "GEOMETRIC_CENTER",
        ]:
            is_accurate = False
        elif geocoder == "arcgis" and location.raw["score"] < 50:
            is_accurate = False
        elif geocoder == "pelias" and location.raw["properties"]["confidence"] < 0.7:
            is_accurate = False

        if not is_accurate:
            logging.debug(f"Geocoding result {location} not accurate enough")
            return False

        if geocoder == "pelias":
            location._address = location.raw["properties"]["label"]

        if address_parts["city"] not in location.address:
            logging.debug(f"Geocoding result {location} does not match city")
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
    geocoding_systems = os.getenv("GEOCODING_ENABLED_SYSTEMS", "")
    if geocoding_systems == "*" or metadata["short_name"] in filter(
        lambda name: len(name), geocoding_systems.split(",")
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
        # TODO: how can we extract the city and state from the metadata?
        address_parts["address"] = extract_address(transcript_txt)
        if address_parts["address"]:
            logging.debug(f"Extracted address with regex: {address_parts['address']}")
            try:
                geo = geocode(address_parts, geocoder=geocoder)
            except:
                geo = None
            if geo:
                return geo

        # If we did not find the address through our regex, then we use the LLM model to extract it as long as the transcript contains a number (possibly indicating an address)
        if (
            llm_model
            and re.search(r"[0-9]", transcript_txt)
            and len(transcript_txt) > 20
        ):
            result = llm.extract_address(llm_model, transcript_txt, metadata)
            if result:
                logging.debug(f"LLM extracted address: {result}")
                address_parts.update(result)

        if address_parts["address"]:
            try:
                return geocode(address_parts, geocoder=geocoder)
            except Exception as e:
                sentry_sdk.capture_exception(e)
                logging.error(f"Got exception while geocoding: {repr(e)}", exc_info=e)


def calculate_route_duration_via_directions(origin: Point, destination: Point) -> int:
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


def calculate_route_duration_via_isochrone(
    origin: Point, destination: Point, max_travel_time: int
) -> int:
    profile = "mapbox/driving-traffic"
    coordinates = f"{origin.longitude},{origin.latitude}"
    duration_thresholds = [
        max_travel_time * 0.25,
        max_travel_time * 0.5,
        max_travel_time * 0.75,
        max_travel_time,
    ]
    duration_thresholds = list(
        set([max(round(threshold / 60), 1) for threshold in duration_thresholds])
    )
    contours_minutes = ",".join([str(x) for x in duration_thresholds])
    url = f"https://api.mapbox.com/isochrone/v1/{profile}/{coordinates}"

    session = CachedSession(
        "isochrone_cache",
        expire_after=timedelta(hours=1),
        ignored_parameters=["access_token"],
    )

    response = session.get(
        url,
        params={
            "contours_minutes": contours_minutes,
            "polygons": "true",
            "access_token": os.getenv("MAPBOX_API_KEY"),
        },
    )
    response.raise_for_status()
    mapbox_response = response.json()

    # sort isochrones by lowest duration first
    mapbox_response["features"].sort(
        key=lambda feature: feature["properties"]["contour"]
    )

    for feature in mapbox_response["features"]:
        if feature["properties"]["contour"] in duration_thresholds:
            polygon = shape(feature["geometry"])
            if polygon.contains(
                ShapePoint(destination.longitude, destination.latitude)
            ):
                # Subtract 1 so we are within the duration threshold when doing the comparison
                return feature["properties"]["contour"] * 60 - 1

    return sys.maxsize

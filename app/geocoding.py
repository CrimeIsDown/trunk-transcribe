import logging
import re
import os
from typing import Tuple, TypedDict

import googlemaps
import sentry_sdk
from geocodio import GeocodioClient
from geocodio.exceptions import GeocodioDataError

from app.metadata import Metadata
from app.transcript import Transcript


class Geo(TypedDict):
    lat: float
    lng: float


class GeoResponse(TypedDict):
    _geo: Geo
    geo_formatted_address: str


google_maps_client = None
geocodio_client = None


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
def extract_address(transcript: str) -> Tuple[str | None, bool]:
    match = re.search(ADDRESS_REGEX, transcript)
    if match:
        if match.group(1) and match.group(2):
            return f"{match.group(2)} and {match.group(3)}", True
        return (
            re.sub(
                r"[-.,]",
                "",
                f"{match.group(4)}{' ' + match.group(5) if match.group(5) else ''} {match.group(6)}",
            ),
            False,
        )
    return None, False


def get_google_maps_client() -> googlemaps.Client | None:  # pragma: no cover
    global google_maps_client
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not google_maps_client and api_key:
        google_maps_client = googlemaps.Client(key=api_key)
    return google_maps_client


def get_geocodio_client() -> GeocodioClient | None:  # pragma: no cover
    global geocodio_client
    api_key = os.getenv("GEOCODIO_API_KEY")
    if not geocodio_client and api_key:
        geocodio_client = GeocodioClient(api_key, timeout=15)
    return geocodio_client


def google_geocode(address: str) -> GeoResponse | None:  # pragma: no cover
    client = get_google_maps_client()
    if not client:
        return None
    geocode_result = client.geocode(  # type: ignore
        address=address,
        components={
            "locality": os.getenv("GEOCODING_CITY"),
            "administrative_area": os.getenv("GEOCODING_STATE"),
            "country": os.getenv("GEOCODING_COUNTRY"),
        },
        bounds=os.getenv("GOOGLE_GEOCODING_BOUNDS"),
    )
    if len(geocode_result) and geocode_result[0]["geometry"]["location_type"] not in [
        "APPROXIMATE",
        "GEOMETRIC_CENTER",
    ]:
        return {
            "_geo": geocode_result[0]["geometry"]["location"],
            "geo_formatted_address": geocode_result[0]["formatted_address"],
        }
    return None


def geocodio_geocode(address: str) -> GeoResponse | None:  # pragma: no cover
    client = get_geocodio_client()
    if not client:
        return None
    try:
        geocode_result = client.geocode_address(
            components={
                "street": address,
                "city": os.getenv("GEOCODING_CITY"),
                "state": os.getenv("GEOCODING_STATE"),
                "country": os.getenv("GEOCODING_COUNTRY"),
            }
        )
    except GeocodioDataError:
        return None

    if "accuracy_type" in geocode_result.best_match and geocode_result.best_match[
        "accuracy_type"
    ] not in [
        "street_center",
        "place",
        "county",
        "state",
    ]:
        return {
            "_geo": geocode_result.best_match["location"],
            "geo_formatted_address": geocode_result.best_match["formatted_address"],
        }

    return None


def geocode(address: str) -> GeoResponse | None:  # pragma: no cover
    if get_geocodio_client():
        return geocodio_geocode(address)
    elif get_google_maps_client():
        return google_geocode(address)
    else:
        return None


def add_geo(doc: dict, metadata: Metadata, transcript: Transcript) -> dict:
    if metadata["short_name"] in filter(
        lambda name: len(name), os.getenv("GEOCODING_ENABLED_SYSTEMS", "").split(",")
    ):
        geo = None
        for segment in transcript.transcript:
            address, _ = extract_address(segment[1])
            if address:
                try:
                    geo = geocode(address)
                except Exception as e:
                    sentry_sdk.capture_exception(e)
                    logging.error(
                        f"Got exception while geocoding: {repr(e)}", exc_info=e
                    )
                if geo:
                    break

        if geo:
            doc.update(geo)
    return doc

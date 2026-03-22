from typing import NotRequired, TypedDict

from geopy.point import Point


class Geo(TypedDict):
    lat: float
    lng: float


class GeoResponse(TypedDict):
    geo: Geo
    geo_formatted_address: str


class AddressParts(TypedDict):
    address: NotRequired[str | None]
    city: str | None
    state: str | None
    country: NotRequired[str | None]
    bounds: NotRequired[list[Point] | None]

from datetime import timedelta
import os
import sys

from shapely.geometry import shape, Point as ShapePoint
from geopy.point import Point
import requests
from requests_cache import CachedSession


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
        timeout=30,
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
        use_temp=True,
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

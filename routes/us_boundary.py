"""Offline USA coordinate check using 2025 Census state cartographic boundaries."""

import json
from functools import lru_cache
from pathlib import Path

BOUNDARY_FILE = Path(__file__).resolve().parents[1] / "data/us-states-2025.json"


@lru_cache(maxsize=1)
def polygons():
    features = json.loads(BOUNDARY_FILE.read_text())
    result = []
    for feature in features:
        geometry = feature["geometry"]
        groups = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        for rings in groups:
            outer = rings[0]
            longitude = [point[0] for point in outer]
            latitude = [point[1] for point in outer]
            result.append(((min(longitude), min(latitude), max(longitude), max(latitude)), rings))
    return result


def in_ring(lon: float, lat: float, ring) -> bool:
    inside = False
    previous = ring[-1]
    for current in ring:
        x1, y1 = previous
        x2, y2 = current
        if (y1 > lat) != (y2 > lat):
            crossing = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < crossing:
                inside = not inside
        previous = current
    return inside


def within_usa(lon: float, lat: float) -> bool:
    for (min_lon, min_lat, max_lon, max_lat), rings in polygons():
        if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
            if in_ring(lon, lat, rings[0]) and not any(in_ring(lon, lat, hole) for hole in rings[1:]):
                return True
    return False

"""Exactly one OSRM route call per uncached request."""

import hashlib
import json
import os
import ssl
import urllib.error
import urllib.request

import certifi
from django.core.cache import cache


class RoutingError(Exception):
    pass


def get_route(start: tuple[float, float], finish: tuple[float, float]) -> dict:
    base_url = os.environ.get("OSRM_BASE_URL", "https://router.project-osrm.org").rstrip("/")
    cache_key = "route:" + hashlib.sha256(repr((base_url, start, finish)).encode()).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    coordinates = f"{start[0]:.6f},{start[1]:.6f};{finish[0]:.6f},{finish[1]:.6f}"
    url = f"{base_url}/route/v1/driving/{coordinates}?overview=simplified&geometries=geojson&steps=false"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "FuelRouteAssessment/1.0 (Django assessment project)"},
    )
    try:
        context = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(request, timeout=18, context=context) as response:
            data = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RoutingError("Routing provider is unavailable. Please retry shortly.") from exc

    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError("No drivable route was found between these locations.")
    route = data["routes"][0]
    geometry = route.get("geometry", {})
    coordinates = geometry.get("coordinates", [])
    if len(coordinates) < 2 or route.get("distance", 0) <= 0:
        raise RoutingError("Routing provider returned an invalid route.")
    result = {
        "distance_miles": route["distance"] / 1609.344,
        "duration_hours": route["duration"] / 3600,
        "coordinates": coordinates,
        "provider": "OSRM",
    }
    cache.set(cache_key, result, timeout=24 * 3600)
    return result

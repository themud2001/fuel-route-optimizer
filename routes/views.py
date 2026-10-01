import json
import math

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .catalog import resolve_city
from .planner import NoFeasibleFuelPlan, build_plan
from .routing import RoutingError, get_route
from .us_boundary import within_usa


def health(request):
    return JsonResponse({"status": "ok"})


def parse_location(value, request_type: str) -> tuple[float, float]:
    if request_type == "state_names":
        if not isinstance(value, str):
            raise ValueError("For type 'state_names', each location must be a 'City, ST' string.")
        return resolve_city(value)
    if request_type != "coordinates":
        raise ValueError("type must be 'state_names' or 'coordinates'.")
    if not isinstance(value, dict):
        raise ValueError("For type 'coordinates', each location must be an object with lat and lon.")
    try:
        lat = float(value.get("lat", value.get("latitude")))
        lon = float(value.get("lon", value.get("longitude")))
    except (TypeError, ValueError) as exc:
        raise ValueError("Coordinates must contain numeric lat and lon.") from exc
    if not math.isfinite(lat) or not math.isfinite(lon):
        raise ValueError("Coordinates must be finite numbers.")
    if not within_usa(lon, lat):
        raise ValueError("Coordinates must be within the USA.")
    return (lon, lat)


@csrf_exempt
def route_plan(request):
    if request.method != "POST":
        response = JsonResponse({"error": "Use POST with a JSON body."}, status=405)
        response["Allow"] = "POST"
        return response
    if len(request.body) > 16_384:
        return JsonResponse({"error": "Request body is too large."}, status=413)
    try:
        payload = json.loads(request.body)
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        request_type = payload.get("type")
        if request_type not in ("state_names", "coordinates"):
            raise ValueError("type must be 'state_names' or 'coordinates'.")
        start = parse_location(payload.get("start"), request_type)
        finish = parse_location(payload.get("finish"), request_type)
        if start == finish:
            raise ValueError("Start and finish must differ.")
        initial_gallons = float(payload.get("initial_fuel_gallons", 50))
        if not math.isfinite(initial_gallons) or not 0 <= initial_gallons <= 50:
            raise ValueError("initial_fuel_gallons must be between 0 and 50.")
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    try:
        route = get_route(start, finish)
        return JsonResponse(
            build_plan(route, start, initial_gallons),
            json_dumps_params={"indent": 2, "ensure_ascii": False},
        )
    except RoutingError as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    except NoFeasibleFuelPlan as exc:
        return JsonResponse({"error": str(exc)}, status=422)

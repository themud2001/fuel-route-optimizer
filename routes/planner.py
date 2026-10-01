"""Fuel planning on a fixed route with a 50-gallon tank and 10 mpg."""

from collections import deque

from .catalog import stations
from .geometry import RouteProjector, haversine

TANK_GALLONS = 50.0
MILES_PER_GALLON = 10.0
MAX_RANGE_MILES = TANK_GALLONS * MILES_PER_GALLON
MAX_DISTANCE_FROM_ROUTE_MILES = 15.0
EPSILON = 1e-7


class NoFeasibleFuelPlan(Exception):
    pass


def candidate_stations(route: dict) -> list[dict]:
    """Keep the cheapest offer at each city location, then project it once."""
    projector = RouteProjector(
        route["coordinates"], route["distance_miles"], MAX_DISTANCE_FROM_ROUTE_MILES
    )
    cheapest_by_city = {}
    for station in stations():
        key = (station["lat"], station["lon"])
        if key not in cheapest_by_city or float(station["price"]) < float(cheapest_by_city[key]["price"]):
            cheapest_by_city[key] = station

    projected = []
    for station in cheapest_by_city.values():
        position = projector.project(
            station["lon"], station["lat"], MAX_DISTANCE_FROM_ROUTE_MILES
        )
        if position and position["mile"] <= route["distance_miles"]:
            projected.append({**station, **position})

    # Stations at the same tenth of a mile are equivalent at this data precision.
    by_mile = {}
    for station in projected:
        key = round(station["mile"], 1)
        if key not in by_mile or float(station["price"]) < float(by_mile[key]["price"]):
            by_mile[key] = station
    return sorted(by_mile.values(), key=lambda station: station["mile"])


def origin_price(start: tuple[float, float]) -> dict:
    nearest = min(
        stations(),
        key=lambda station: haversine(start[0], start[1], station["lon"], station["lat"]),
    )
    return {
        "price_usd_per_gallon": float(nearest["price"]),
        "reference_city": f"{nearest['city']}, {nearest['state']}",
        "distance_miles": round(
            haversine(start[0], start[1], nearest["lon"], nearest["lat"]), 1
        ),
    }


def optimize_fuel(
    candidates: list[dict], distance_miles: float, initial_gallons: float, initial_price: float
) -> dict:
    """Find minimum-cost purchases at route-projected candidate positions.

    At each candidate, buy just enough to reach the next equal/cheaper station
    within tank range; otherwise fill only as much as the remainder needs.
    This is optimal for fixed ordered locations and prices with no detour cost.
    """
    prices = [float(station["price"]) for station in candidates]
    next_cheaper = [None] * len(candidates)
    stack = []
    for index in range(len(candidates) - 1, -1, -1):
        while stack and prices[stack[-1]] > prices[index]:
            stack.pop()
        next_cheaper[index] = stack[-1] if stack else None
        stack.append(index)

    fuel = initial_gallons
    position = 0.0
    lots = deque([[initial_gallons, initial_price, True]]) if initial_gallons else deque()
    consumed_cost = 0.0
    initial_consumed_cost = 0.0
    cash_spent = 0.0
    stops = []

    def travel_to(next_mile: float) -> None:
        nonlocal fuel, position, consumed_cost, initial_consumed_cost
        needed = (next_mile - position) / MILES_PER_GALLON
        if needed > fuel + EPSILON:
            raise NoFeasibleFuelPlan(
                "No feasible fuel plan: a required segment exceeds available fuel. "
                "Try a route with more stations in the price dataset."
            )
        fuel = max(0.0, fuel - needed)
        while needed > EPSILON:
            quantity, price, is_initial = lots[0]
            burned = min(quantity, needed)
            consumed_cost += burned * price
            if is_initial:
                initial_consumed_cost += burned * price
            quantity -= burned
            needed -= burned
            if quantity <= EPSILON:
                lots.popleft()
            else:
                lots[0][0] = quantity
        position = next_mile

    for index, station in enumerate(candidates):
        mile = station["mile"]
        travel_to(mile)
        cheaper = next_cheaper[index]
        if cheaper is not None and candidates[cheaper]["mile"] - mile <= MAX_RANGE_MILES:
            target_miles = candidates[cheaper]["mile"] - mile
        else:
            target_miles = min(MAX_RANGE_MILES, distance_miles - mile)
        buy = max(0.0, target_miles / MILES_PER_GALLON - fuel)
        if buy <= EPSILON:
            continue
        if fuel + buy > TANK_GALLONS + EPSILON:
            raise NoFeasibleFuelPlan("Fuel plan exceeded the vehicle's tank capacity.")
        price = prices[index]
        fuel += buy
        lots.append([buy, price, False])
        cost = buy * price
        cash_spent += cost
        stops.append(
            {
                "station_id": station["id"],
                "station_name": station["name"],
                "address": station["address"],
                "city": station["city"],
                "state": station["state"],
                "mile_marker": round(mile, 1),
                "estimated_distance_from_route_miles": round(station["distance_to_route_miles"], 1),
                "route_coordinate": station["route_coordinate"],
                "city_coordinate_estimate": [station["lon"], station["lat"]],
                "price_usd_per_gallon": round(price, 6),
                "gallons_to_buy": round(buy, 2),
                "purchase_cost_usd": round(cost, 2),
            }
        )

    travel_to(distance_miles)
    return {
        "stops": stops,
        "fuel_used_gallons": round(distance_miles / MILES_PER_GALLON, 2),
        "initial_fuel_gallons": round(initial_gallons, 2),
        "fuel_remaining_gallons": round(fuel, 2),
        "en_route_purchases_usd": round(cash_spent, 2),
        "initial_fuel_consumed_value_usd": round(initial_consumed_cost, 2),
        "total_fuel_cost_usd": round(consumed_cost, 2),
    }


def build_plan(route: dict, start: tuple[float, float], initial_gallons: float) -> dict:
    initial_reference = origin_price(start) if initial_gallons else None
    candidates = candidate_stations(route)
    plan = optimize_fuel(
        candidates,
        route["distance_miles"],
        initial_gallons,
        initial_reference["price_usd_per_gallon"] if initial_reference else 0.0,
    )
    features = [
        {
            "type": "Feature",
            "properties": {"kind": "route"},
            "geometry": {"type": "LineString", "coordinates": route["coordinates"]},
        }
    ]
    for number, stop in enumerate(plan["stops"], start=1):
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "kind": "fuel_stop",
                    "stop_number": number,
                    "station_name": stop["station_name"],
                    "location_precision": "route projection from city centroid",
                },
                "geometry": {"type": "Point", "coordinates": stop["route_coordinate"]},
            }
        )
    return {
        "route": {
            "distance_miles": round(route["distance_miles"], 1),
            "duration_hours": round(route["duration_hours"], 1),
            "provider": route["provider"],
        },
        "vehicle": {"tank_capacity_gallons": TANK_GALLONS, "max_range_miles": 500, "mpg": 10},
        **plan,
        "initial_fuel_price_estimate": initial_reference,
        "map": {"type": "FeatureCollection", "features": features},
        "assumptions": [
            "The route is fixed; station choices minimize fuel purchase cost along it.",
            "Station locations are estimated from city postal coordinates, not exact pump coordinates.",
            "Stops are considered when their city estimate is within 15 straight-line miles of the route; detour time and fuel are not included.",
            "Total fuel cost values only the fuel consumed on this trip. Starting fuel is priced using the nearest station's city-level price as an estimate.",
        ],
        "attribution": {
            "routing": "OSRM / OpenStreetMap contributors",
            "station_locations": "GeoNames postal code data, CC BY 4.0",
            "us_boundaries": "U.S. Census Bureau 2025 cartographic boundary files",
        },
    }

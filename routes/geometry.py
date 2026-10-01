"""Project estimated city positions onto a route without extra routing calls."""

import math
from collections import defaultdict

EARTH_MILES = 3958.7613
CELL_DEGREES = 0.5


def haversine(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    a1, a2 = math.radians(lat1), math.radians(lat2)
    da = a2 - a1
    do = math.radians(lon2 - lon1)
    value = math.sin(da / 2) ** 2 + math.cos(a1) * math.cos(a2) * math.sin(do / 2) ** 2
    return 2 * EARTH_MILES * math.asin(min(1, math.sqrt(value)))


class RouteProjector:
    def __init__(self, coordinates: list[list[float]], distance_miles: float, radius_miles: float):
        self.coordinates = coordinates
        self.distance_miles = distance_miles
        self.lengths = []
        self.cumulative = [0.0]
        self.grid = defaultdict(list)
        for index, (a, b) in enumerate(zip(coordinates, coordinates[1:])):
            segment_miles = haversine(a[0], a[1], b[0], b[1])
            self.lengths.append(segment_miles)
            self.cumulative.append(self.cumulative[-1] + segment_miles)
            middle_lat = (a[1] + b[1]) / 2
            lat_margin = radius_miles / 69.0
            lon_margin = radius_miles / max(15.0, 69.0 * math.cos(math.radians(middle_lat)))
            x0 = math.floor((min(a[0], b[0]) - lon_margin) / CELL_DEGREES)
            x1 = math.floor((max(a[0], b[0]) + lon_margin) / CELL_DEGREES)
            y0 = math.floor((min(a[1], b[1]) - lat_margin) / CELL_DEGREES)
            y1 = math.floor((max(a[1], b[1]) + lat_margin) / CELL_DEGREES)
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    self.grid[(x, y)].append(index)

    def project(self, lon: float, lat: float, radius_miles: float) -> dict | None:
        cell = (math.floor(lon / CELL_DEGREES), math.floor(lat / CELL_DEGREES))
        best = None
        for index in self.grid.get(cell, []):
            a, b = self.coordinates[index : index + 2]
            lon_scale = 69.172 * math.cos(math.radians((a[1] + b[1] + lat) / 3))
            ax, ay = a[0] * lon_scale, a[1] * 69.0
            bx, by = b[0] * lon_scale, b[1] * 69.0
            px, py = lon * lon_scale, lat * 69.0
            dx, dy = bx - ax, by - ay
            length_squared = dx * dx + dy * dy
            fraction = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_squared)) if length_squared else 0.0
            route_lon = a[0] + fraction * (b[0] - a[0])
            route_lat = a[1] + fraction * (b[1] - a[1])
            distance = haversine(lon, lat, route_lon, route_lat)
            if best is None or distance < best["distance_to_route_miles"]:
                raw_mile = self.cumulative[index] + fraction * self.lengths[index]
                mile = raw_mile * self.distance_miles / self.cumulative[-1]
                best = {
                    "mile": mile,
                    "distance_to_route_miles": distance,
                    "route_coordinate": [round(route_lon, 6), round(route_lat, 6)],
                }
        return best if best and best["distance_to_route_miles"] <= radius_miles else None

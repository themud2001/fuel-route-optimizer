import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from .geometry import RouteProjector
from .planner import NoFeasibleFuelPlan, build_plan, optimize_fuel
from .routing import get_route
from .us_boundary import within_usa


def candidate(mile, price):
    return {
        "mile": float(mile),
        "price": str(price),
        "id": str(mile),
        "name": f"Station {mile}",
        "address": "I-1",
        "city": "Test",
        "state": "TX",
        "distance_to_route_miles": 0.0,
        "route_coordinate": [-100.0, 35.0],
        "lon": -100.0,
        "lat": 35.0,
    }


class FuelPlannerTests(SimpleTestCase):
    def test_multiple_stops_and_partial_fills(self):
        plan = optimize_fuel(
            [candidate(400, 4), candidate(700, 3), candidate(900, 5)],
            distance_miles=1000,
            initial_gallons=50,
            initial_price=3.5,
        )
        self.assertEqual([stop["mile_marker"] for stop in plan["stops"]], [400, 700])
        self.assertEqual([stop["gallons_to_buy"] for stop in plan["stops"]], [20, 30])
        self.assertEqual(plan["en_route_purchases_usd"], 170)
        self.assertEqual(plan["total_fuel_cost_usd"], 345)
        self.assertEqual(plan["fuel_remaining_gallons"], 0)

    def test_short_route_prices_only_consumed_starting_fuel(self):
        plan = optimize_fuel([], 100, 50, 3.5)
        self.assertEqual(plan["stops"], [])
        self.assertEqual(plan["total_fuel_cost_usd"], 35)
        self.assertEqual(plan["en_route_purchases_usd"], 0)

    def test_empty_tank_purchases_at_start(self):
        plan = optimize_fuel([candidate(0, 3)], 100, 0, 0)
        self.assertEqual(plan["stops"][0]["gallons_to_buy"], 10)
        self.assertEqual(plan["total_fuel_cost_usd"], 30)

    def test_gap_over_range_is_reported(self):
        with self.assertRaises(NoFeasibleFuelPlan):
            optimize_fuel([candidate(600, 3)], 800, 50, 3)

    def test_projects_nearby_city_onto_route(self):
        projector = RouteProjector([[-100.0, 35.0], [-99.0, 35.0]], 60, 15)
        point = projector.project(-99.5, 35.1, 15)
        self.assertIsNotNone(point)
        self.assertAlmostEqual(point["mile"], 30, delta=1)
        self.assertIsNone(projector.project(-99.5, 36.0, 15))

    def test_public_response_contains_only_route_stops_cost_and_map(self):
        route = {
            "distance_miles": 1000,
            "duration_hours": 16.2,
            "coordinates": [[-100.0, 35.0], [-90.0, 35.0]],
        }
        with patch("routes.planner.candidate_stations") as mocked_stations, patch(
            "routes.planner.origin_price"
        ) as mocked_origin_price:
            mocked_stations.return_value = [
                candidate(400, 4), candidate(700, 3), candidate(900, 5)
            ]
            mocked_origin_price.return_value = {"price_usd_per_gallon": 3.5}
            response = build_plan(route, (-100.0, 35.0), 50)

        self.assertEqual(set(response), {"route", "stops", "total_fuel_cost_usd", "map"})
        self.assertEqual(response["route"], {"distance_miles": 1000, "duration_hours": 16.2})
        self.assertEqual(response["total_fuel_cost_usd"], 345)
        self.assertEqual(len(response["stops"]), 2)
        self.assertEqual(
            set(response["stops"][0]),
            {
                "station_name", "address", "mile_marker", "price_usd_per_gallon",
                "gallons_to_buy", "cost_usd",
            },
        )
        self.assertEqual(response["stops"][0]["address"], "I-1, Test, TX")
        self.assertEqual(len(response["map"]["features"]), 3)
        self.assertEqual(response["map"]["features"][1]["properties"]["stop_number"], 1)


class ApiTests(SimpleTestCase):
    def test_rejects_invalid_input(self):
        response = self.client.post(
            "/api/v1/route/",
            data=json.dumps({"start": "Chicago", "finish": "Denver, CO"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_coordinate_validation_uses_us_boundary(self):
        self.assertTrue(within_usa(-87.6298, 41.8781))  # Chicago
        self.assertFalse(within_usa(-79.3832, 43.6532))  # Toronto

    @patch("routes.views.build_plan")
    @patch("routes.views.get_route")
    def test_accepts_city_state_input(self, mocked_route, mocked_plan):
        mocked_route.return_value = {"distance_miles": 1}
        mocked_plan.return_value = {"total_fuel_cost_usd": 10}
        response = self.client.post(
            "/api/v1/route/",
            data=json.dumps({"start": "Chicago, IL", "finish": "Denver, CO"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_fuel_cost_usd"], 10)
        self.assertIn(b'\n  "total_fuel_cost_usd": 10\n', response.content)
        self.assertEqual(mocked_route.call_count, 1)

    @patch("routes.routing.urllib.request.urlopen")
    def test_identical_route_uses_one_provider_call(self, mocked_open):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def read(self):
                return json.dumps(
                    {
                        "code": "Ok",
                        "routes": [
                            {
                                "distance": 160934.4,
                                "duration": 7200,
                                "geometry": {
                                    "coordinates": [[-90, 35], [-89, 35]],
                                },
                            }
                        ],
                    }
                ).encode()

        mocked_open.return_value = Response()
        cache.clear()
        first = get_route((-90, 35), (-89, 35))
        second = get_route((-90, 35), (-89, 35))
        self.assertEqual(first, second)
        self.assertEqual(mocked_open.call_count, 1)

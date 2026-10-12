"""Road network, scenarios, environment and metrics."""
import random

import pytest

from engine.city import CUSTOMER, NETWORK, RESTAURANT, ROUTE_PATHS, TILE_KM
from engine.environment import DeliveryEnvironment, reward
from engine.metrics import execute_runs, run_rng, summarize
from engine.scenarios import SCENARIOS, get_scenario
from engine.world import ROUTE_FACTS, Traffic, Weather, evaluate_route


def test_every_route_is_a_continuous_path_from_restaurant_to_customer():
    for rid, path in ROUTE_PATHS.items():
        assert NETWORK.is_valid_path(path, RESTAURANT, CUSTOMER), rid
        assert len(NETWORK.path_edges(path)) == len(path) - 1


def test_route_lengths_come_from_the_map_geometry():
    for rid, path in ROUTE_PATHS.items():
        tiles = sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(path, path[1:]))
        assert ROUTE_FACTS[rid]["distance_km"] == pytest.approx(tiles * TILE_KM)


def test_broken_path_is_rejected():
    assert not NETWORK.is_valid_path([(4, 12), (14, 12), (29, 12)], RESTAURANT, CUSTOMER)   # skips intersections
    assert not NETWORK.is_valid_path(ROUTE_PATHS["A"][:-1], RESTAURANT, CUSTOMER)


def test_three_mandatory_situations():
    assert [s.id for s in SCENARIOS] == [1, 2, 3]
    s1, s2, s3 = SCENARIOS
    assert s1.weather == "clear" and all(v == "normal" for v in s1.traffic.values())
    assert s2.traffic["downtown"] == "heavy" and len({s2.traffic[z] for z in ("downtown", "ring", "oldtown", "expressway")}) > 1
    assert s3.weather == "rain" and s3.order.urgent and s3.traffic["downtown"] == "heavy"


def test_percepts_hide_offline_sensors():
    env = DeliveryEnvironment(get_scenario(2))
    early, latest = env.percepts()
    assert latest.is_latest and latest.reports["B"] is None
    assert early.reports["B"] == "light"


def test_rain_slows_and_floods():
    clear = evaluate_route("C", Traffic(), Weather("clear"))
    rain = evaluate_route("C", Traffic(), Weather("rain"))
    assert rain.travel_min > clear.travel_min * 1.2 and rain.flood_km > 0 and rain.safety < clear.safety


def test_execution_is_reproducible_and_consistent():
    sc = get_scenario(3)
    env = DeliveryEnvironment(sc)
    a, b = env.execute("D", random.Random(5)), env.execute("D", random.Random(5))
    assert a.as_dict() == b.as_dict()
    t = sc.order.prep_min
    for s in a.segments:                      # contiguous in time and along the path
        assert s.start == pytest.approx(t) and s.end == pytest.approx(s.start + s.drive_min + s.wait_min)
        t = s.end
    assert [s.a for s in a.segments] + [a.segments[-1].b] == ROUTE_PATHS["D"]
    assert a.total_min == pytest.approx(sc.order.prep_min + a.travel_min)


def test_deadline_logic_never_reports_a_late_delivery_as_on_time():
    sc = get_scenario(3)
    for trip in execute_runs(sc, "A", 100, 1) + execute_runs(sc, "D", 100, 1):
        assert trip.on_time == (trip.total_min <= sc.order.deadline_min)
        assert trip.late_min == pytest.approx(max(0.0, trip.total_min - sc.order.deadline_min))
    assert summarize(execute_runs(sc, "A", 100, 1))["on_time"] == 0.0   # the jammed downtown route cannot make it


def test_reward_formula():
    assert reward(True, 0, False, 2.0, 0.9, False) == pytest.approx(10 - 0.6 - 1.5)
    assert reward(False, 3, True, 2.0, 0.9, True) == pytest.approx(-2.4 - 5 - 0.6 - 1.5 - 10)


def test_common_random_numbers():
    assert run_rng(42, 2, 7).random() == run_rng(42, 2, 7).random()
    assert run_rng(42, 2, 7).random() != run_rng(42, 2, 8).random()

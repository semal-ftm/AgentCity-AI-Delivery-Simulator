"""The optional second source -> destination (delivery 2, top to bottom of the map)."""
import pytest

from agents import AGENT_CLASSES, Brain, make_agent
from engine.city import DELIVERIES, NETWORK
from engine.environment import DeliveryEnvironment
from engine.metrics import execute_runs, summarize
from engine.scenarios import SCENARIOS, get_scenario
from sim.runner import build_run


@pytest.fixture(scope="module")
def brain2():
    b = Brain()
    b.train(1500, 42, delivery=2)
    return b


def test_delivery2_routes_are_real_paths_from_top_to_bottom():
    D = DELIVERIES[2]
    assert D["restaurant"][1] < D["customer"][1]                       # restaurant is north of the customer
    for rid, path in D["paths"].items():
        assert NETWORK.is_valid_path(path, D["restaurant"], D["customer"]), rid
    assert set(D["paths"]) == {"A", "B", "C", "D"}


def test_delivery1_is_unchanged_by_default():
    sc = get_scenario(2)
    assert sc.delivery == 1 and get_scenario(2, 1) is sc
    assert DeliveryEnvironment(sc).percepts()[0].delivery == 1


def test_same_situations_on_delivery2():
    for base in SCENARIOS:
        sc = get_scenario(base.id, 2)
        assert (sc.weather, sc.traffic, sc.order.urgent) == (base.weather, base.traffic, base.order.urgent)
        assert sc.order.deadline_min == base.order.deadline_min + DELIVERIES[2]["extra_min"]


def test_all_agents_decide_and_explain_on_delivery2(brain2):
    for base in SCENARIOS:
        sc = get_scenario(base.id, 2)
        for cls in AGENT_CLASSES:
            a = make_agent(cls.key, brain2)
            a.reset()
            for p in DeliveryEnvironment(sc).percepts():
                a.perceive(p)
            d = a.decide()
            assert d.route in "ABCD" and set(a.route_notes) == set("ABCD")


def test_learning_agent_learns_the_best_route_on_delivery2(brain2):
    s = brain2.summary()
    assert s["last_avg"] > s["first_avg"]
    for base in SCENARIOS:
        sc = get_scenario(base.id, 2)
        run = build_run(sc, "learning", brain2, 42, 0, 200)
        best = max("ABCD", key=lambda r: summarize(execute_runs(sc, r, 200, 42))["reward"])
        assert run["decision"]["route"] == best, (base.id, run["decision"]["route"], best)


def test_rider_follows_delivery2_roads(brain2):
    run = build_run(get_scenario(3, 2), "contextual", brain2, 42, 0, 20)
    segs = run["trip"]["segments"]
    assert tuple(segs[0]["a"]) == DELIVERIES[2]["restaurant"] and tuple(segs[-1]["b"]) == DELIVERIES[2]["customer"]

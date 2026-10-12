"""Replayable timelines, agent switching, comparison and the HTTP API."""
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from agents import Brain
from engine.city import NETWORK
from engine.environment import DeliveryEnvironment
from engine.metrics import run_rng
from engine.scenarios import get_scenario
from server import App, make_handler
from sim.runner import build_run, compare

ORDER = ["observe", "reason", "decide", "act", "respond", "result"]


@pytest.fixture(scope="module")
def brain():
    b = Brain()
    b.train(800, 42)
    return b


def test_timeline_has_six_phases_in_order(brain):
    run = build_run(get_scenario(2), "model_based", brain, 42, 0, 50)
    phases = [s["phase"] for s in run["steps"]]
    assert [p for i, p in enumerate(phases) if i == 0 or p != phases[i - 1]] == ORDER
    acts = [s for s in run["steps"] if s["phase"] == "act"]
    for a, b in zip(acts, acts[1:]):
        assert a["t"][1] == pytest.approx(b["t"][0])                     # ride steps are back to back
    assert run["steps"][-1]["t"][1] == pytest.approx(run["trip"]["total_min"], abs=0.01)


def test_animated_trip_equals_the_simulated_execution(brain):
    sc = get_scenario(3)
    run = build_run(sc, "contextual", brain, 42, 7, 20)
    trip = DeliveryEnvironment(sc).execute(run["decision"]["route"], run_rng(42, 3, 7))
    assert run["trip"] == trip.as_dict()
    for seg in run["trip"]["segments"]:                                  # rider follows real road edges
        NETWORK.edge(tuple(seg["a"]), tuple(seg["b"]))


def test_switching_agents_keeps_the_scenario_and_isolates_state(brain):
    sc = get_scenario(2)
    r1 = build_run(sc, "simple_reflex", brain, 42, 0, 20)
    build_run(sc, "learning", brain, 42, 0, 20)
    build_run(sc, "model_based", brain, 42, 0, 20)
    r1b = build_run(sc, "simple_reflex", brain, 42, 0, 20)
    assert r1 == r1b                                                     # nothing leaked between runs
    assert r1["scenario"] == build_run(sc, "utility_based", brain, 42, 0, 20)["scenario"]


def test_compare_uses_same_conditions(brain):
    rows = compare(get_scenario(3), brain, 42, 50)
    assert len(rows) == 7
    by_route = {}
    for r in rows:
        key = r["route"]
        metrics = {k: r[k] for k in ("time", "cost", "safety", "on_time", "reward")}
        assert by_route.setdefault(key, metrics) == metrics              # same route -> identical results


@pytest.fixture(scope="module")
def base():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(App(episodes=400, save=False)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def call(base, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        raw = r.read()
        return json.loads(raw) if r.headers.get_content_type() == "application/json" else raw.decode()


def test_api(base):
    init = call(base, "/api/init")
    assert len(init["agents"]) == 7 and len(init["situations"]) == 3 and init["world"]["routes"]
    run = call(base, "/api/run", {"situation": 3, "agent": "hierarchical", "run_index": 2})
    assert run["decision"]["route"] == "D" and run["steps"]
    assert len(call(base, "/api/compare", {"situation": 1})["rows"]) == 7
    assert "<svg" in call(base, "/api/diagram/goal_based.svg") and "<svg" in call(base, "/api/diagram/system.svg")
    assert "Agent City" in call(base, "/")
    t = call(base, "/api/train", {"episodes": 200, "seed": 1})
    assert t["episodes"] == 200
    assert len(call(base, "/api/test_policy", {"runs": 20})["rows"]) == 3


def test_api_delivery2(base):
    init = call(base, "/api/init")
    assert set(init["world"]["deliveries"]) == {"1", "2"} and init["learning_by_delivery"]["2"]["delivery"] == 2
    run = call(base, "/api/run", {"situation": 2, "agent": "model_based", "run_index": 0, "delivery": 2})
    assert run["scenario"]["delivery"] == 2 and run["route_reasons"]
    rows = call(base, "/api/compare_all?delivery=2")
    assert len(rows) == 3 and all(r["delivery"] == 2 for r in rows)

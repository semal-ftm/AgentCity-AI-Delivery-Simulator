"""Simulation runner: one agent, one situation -> a step-by-step, replayable timeline.

The timeline follows six phases:
  1 observe  - the situation and the agent's own percepts
  2 reason   - the agent's internal steps (written by the agent itself)
  3 decide   - the chosen action and why
  4 act      - the rider executes the route on the road network (timed segments)
  5 respond  - the environment's effects: traffic delay, red lights, incidents
  6 result   - performance measure (and, for the learning agent, its Q-update)

Every step is stored, so "previous step" in the dashboard restores a stored step
instead of recomputing the decision.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from agents import REGISTRY, Brain, make_agent
from engine.city import NETWORK, ROUTE_IDS
from engine.environment import DeliveryEnvironment, Trip
from engine.metrics import execute_runs, run_rng, stream_id, summarize
from engine.scenarios import Scenario


def edge_conditions(scenario: Scenario) -> List[dict]:
    """True traffic level of every road segment, for drawing congestion on the map."""
    t, w = scenario.traffic_model, scenario.weather_model
    return [{"a": e.a, "b": e.b, "level": t.level(e.street.zone), "flooded": w.flooded(e)} for e in NETWORK.edges.values()]


def situation_step(sc: Scenario) -> dict:
    o = sc.order
    return {"phase": "observe", "kind": "env", "title": "The situation",
            "text": (f"{sc.clock} ({sc.time_of_day}), weather {sc.weather}. Order {o.order_id}: {o.food} from {o.restaurant} "
                     f"to {o.customer}. Ready in {o.prep_min:g} min, deadline {o.deadline_min:g} min"
                     f"{', URGENT' if o.urgent else ''}. Four candidate routes A-D connect the restaurant to the customer."),
            "data": {"scenario": sc.id}, "focus": list(ROUTE_IDS), "marks": {}, "t": [0, 0]}


def _group_segments(trip: Trip) -> List[dict]:
    groups: List[dict] = []
    for s in trip.segments:
        if groups and groups[-1]["street"] == s.street:
            g = groups[-1]
            g["segs"].append(s)
        else:
            groups.append({"street": s.street, "segs": [s]})
    return groups


def build_run(sc: Scenario, agent_key: str, brain: Optional[Brain], seed: int = 42, run_index: int = 0,
              mc_runs: int = 200) -> dict:
    env = DeliveryEnvironment(sc)
    agent = make_agent(agent_key, brain)
    agent.reset()
    for p in env.percepts():
        agent.perceive(p)
    decision = agent.decide()
    steps: List[dict] = [situation_step(sc)]
    for s in agent.trace.steps:
        d = s.as_dict()
        d["t"] = [0, 0]
        steps.append(d)

    trip = env.execute(decision.route, run_rng(seed, stream_id(sc), run_index))
    o = sc.order

    # --- act: pick up
    agent.on_execution("pickup", {"prep": o.prep_min})
    steps.append({"phase": "act", "kind": "pickup", "title": "Pick up the food",
                  "text": f"The rider waits {o.prep_min:g} min at {o.restaurant} while the food is prepared, then departs on route {decision.route}."
                          + (" The customer is notified that the order may be late." if decision.notify_customer else ""),
                  "focus": [decision.route], "marks": {decision.route: "chosen"}, "t": [0, o.prep_min],
                  "snapshot": agent.snapshot()})
    agent.on_execution("ride", {"route": decision.route})
    # --- act: ride, one step per street
    for g in _group_segments(trip):
        segs = g["segs"]
        street = NETWORK.edge(segs[0].a, segs[0].b).street
        km = sum(s.km for s in segs)
        drive = sum(s.drive_min for s in segs)
        wait = sum(s.wait_min for s in segs)
        notes = [s.incident for s in segs if s.incident]
        lvl = segs[0].level
        steps.append({"phase": "act", "kind": "ride", "title": f"Ride {street.name}",
                      "text": f"{km:.1f} km of {street.kind} road with {lvl} traffic: {drive:.1f} min driving"
                              + (f" + {wait:.1f} min at red lights" if wait > 0.05 else "") + "."
                              + (f" INCIDENT: {notes[0]}." if notes else ""),
                      "data": {"street": street.id, "km": round(km, 2), "drive": round(drive, 2), "wait": round(wait, 2), "level": lvl,
                               "incident": notes[0] if notes else None},
                      "focus": [decision.route], "marks": {decision.route: "chosen"},
                      "t": [round(segs[0].start, 3), round(segs[-1].end, 3)], "snapshot": agent.snapshot()})

    # --- respond: what the environment did
    free = sum(s.km / NETWORK.edge(s.a, s.b).street.speed_kmh * 60 for s in trip.segments)
    waits = sum(s.wait_min for s in trip.segments)
    drive = trip.travel_min - waits
    pred = decision.predicted_total_min
    agent.on_execution("delivered", {"route": trip.route, "travel": trip.travel_min, "total": trip.total_min,
                                     "on_time": trip.on_time, "late": trip.late_min})
    steps.append({"phase": "respond", "kind": "response", "title": "Environment response",
                  "text": (f"Free-flow riding time would be {free:.1f} min. Traffic, weather and today's random variation made it "
                           f"{drive:.1f} min, plus {waits:.1f} min at red lights" + (" and an incident delay" if trip.incident else "") +
                           f". Delivered at {trip.total_min:.1f} min"
                           + (f" (the agent predicted {pred:.1f} min)" if pred is not None else " (this agent made no time prediction)") + "."),
                  "data": {"free_flow": round(free, 2), "driving": round(drive, 2), "signals": round(waits, 2),
                           "incident": trip.incident, "predicted": None if pred is None else round(pred, 2),
                           "actual": round(trip.total_min, 2), "events": trip.events},
                  "focus": [decision.route], "marks": {decision.route: "chosen"},
                  "t": [round(trip.total_min, 3), round(trip.total_min, 3)], "snapshot": agent.snapshot()})

    learning = agent.learn(trip)
    mc = summarize(execute_runs(sc, decision.route, mc_runs, seed))
    verdict = "ON TIME" if trip.on_time else f"LATE by {trip.late_min:.1f} min"
    steps.append({"phase": "result", "kind": "result", "title": f"Delivered - {verdict}",
                  "text": (f"Total {trip.total_min:.1f} min vs deadline {o.deadline_min:g}; cost {trip.cost:.2f} CU; safety {trip.safety:.2f}; "
                           f"reward {trip.reward:+.2f}. Over {mc['runs']} simulated runs of this decision: {mc['on_time']}% on time, "
                           f"mean {mc['time']} min, mean reward {mc['reward']:+.2f}."),
                  "data": {"trip": {k: v for k, v in trip.as_dict().items() if k != "segments"}, "mc": mc},
                  "focus": [decision.route], "marks": {decision.route: "chosen"},
                  "t": [round(trip.total_min, 3), round(trip.total_min, 3)], "snapshot": agent.snapshot()})
    if learning:
        steps.append({"phase": "result", "kind": "learn", "title": "Learning from this delivery",
                      "text": f"Reward {learning['reward']:+.2f} updates the Q-value: {learning['formula']}. "
                              "(The update is applied to this run's own copy of the Q-table, so replays stay reproducible.)",
                      "data": learning, "focus": [decision.route], "marks": {decision.route: "chosen"},
                      "t": [round(trip.total_min, 3), round(trip.total_min, 3)]})
    for i, s in enumerate(steps):
        s["i"] = i
    outcomes = {r: (mc if r == decision.route else summarize(execute_runs(sc, r, mc_runs, seed))) for r in ROUTE_IDS}
    best = max(ROUTE_IDS, key=lambda r: outcomes[r]["reward"])
    return {
        "route_reasons": agent.route_notes, "route_outcomes": outcomes, "best_route": best, "fired_rules": list(agent.fired),
        "scenario": sc.to_dict(), "agent": REGISTRY[agent_key].meta(), "seed": seed, "run_index": run_index,
        "decision": decision.as_dict(), "trip": trip.as_dict(), "mc": mc, "steps": steps,
        "edges": edge_conditions(sc),
        "truth": {r: env.true_estimate(r).as_dict() for r in ROUTE_IDS},
    }


def compare(sc: Scenario, brain: Optional[Brain], seed: int = 42, runs: int = 200) -> List[dict]:
    """All seven agents on the same situation, the same evaluation rules and the same random seeds."""
    rows = []
    cache: Dict[str, dict] = {}
    for key, cls in REGISTRY.items():
        agent = make_agent(key, brain)
        agent.reset()
        for p in DeliveryEnvironment(sc).percepts():
            agent.perceive(p)
        d = agent.decide()
        if d.route not in cache:
            cache[d.route] = summarize(execute_runs(sc, d.route, runs, seed))
        utility = None
        if key == "utility_based":
            utility = next(s.data["rows"] for s in reversed(agent.trace.steps) if s.kind == "utility")
            utility = next(r["utility"] for r in utility if r["route"] == d.route)
        rows.append({"agent": key, "name": cls.name, "short": cls.short, "color": cls.color,
                     "strategy": cls.architecture, "route": d.route, "notify": d.notify_customer, "reason": d.reason,
                     "predicted": None if d.predicted_total_min is None else round(d.predicted_total_min, 1),
                     "utility": utility, "deadline": sc.order.deadline_min, **cache[d.route]})
    return rows

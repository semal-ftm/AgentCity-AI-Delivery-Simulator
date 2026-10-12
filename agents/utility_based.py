"""Agent 4 - Utility-Based Agent.

Scores EVERY route with a numeric utility function that trades off several factors,
and picks the route with the highest utility. All factor scores are on a 0-100 scale:

    TimeScore     = 100 x (fastest predicted travel time / this route's travel time)
    SafetyScore   = 100 x predicted safety (0..1)
    CostScore     = 100 x (cheapest predicted cost / this route's cost)
    DistanceScore = 100 x (shortest distance / this route's distance)

    Utility = 0.40 x TimeScore + 0.30 x SafetyScore + 0.20 x CostScore + 0.10 x DistanceScore

The weights are FIXED: the agent values the four factors the same way in every situation.
"""
from __future__ import annotations

from typing import List

from engine.environment import Percept

from .base import Agent, Decision, by_distance, latest_known, predict

WEIGHTS = {"time": 0.40, "safety": 0.30, "cost": 0.20, "distance": 0.10}


class UtilityBasedAgent(Agent):
    key = "utility_based"
    name = "Utility-Based Agent"
    short = "Utility-Based"
    architecture = "Weighted multi-factor utility; choose the maximum"
    color = "#06d6a0"
    RULEBOOK = [
        {"title": "Step 1: estimate every route", "rules": [
            {"id": "U1", "text": "For every route, the agent estimates the riding time, the cost, how safe it is and how long it is, using the latest traffic, the weather, flooding, traffic lights and tolls."},
        ]},
        {"title": "Step 2: give each route four scores out of 100 (higher is better)", "rules": [
            {"id": "U2", "text": "Time score: the fastest route gets 100, and slower routes get less in proportion to how much slower they are."},
            {"id": "U3", "text": "Safety score: the route's predicted safety turned into a mark out of 100."},
            {"id": "U4", "text": "Cost score: the cheapest route gets 100, and more expensive routes get less in proportion."},
            {"id": "U5", "text": "Distance score: the shortest route gets 100, and longer routes get less in proportion."},
        ]},
        {"title": "Step 3: combine the scores and choose", "rules": [
            {"id": "U6", "text": "The overall score (utility) is 40% time + 30% safety + 20% cost + 10% distance. These percentages never change, whatever the situation."},
            {"id": "U7", "text": "The agent takes the route with the highest overall score. It does not treat the deadline as a strict limit."},
        ]},
    ]
    info = {
        "definition": "A utility-based agent assigns a numeric 'happiness' (utility) to each possible outcome and chooses the action with the highest expected utility.",
        "principle": "for each route: predict time, cost, safety, distance -> normalise to 0-100 -> weighted sum -> choose argmax.",
        "logic": "Utility = 0.40·Time + 0.30·Safety + 0.20·Cost + 0.10·Distance. TimeScore, CostScore and DistanceScore compare each route with the best route (best = 100). SafetyScore is the predicted safety x 100. Traffic beliefs are the latest known report per route (a missing report falls back to the previous feed).",
        "example": "Rush hour: B scores highest because it is fastest and safest, although C is shorter.",
        "advantages": ["Balances several goals instead of one", "Every decision is a transparent calculation", "Picks the best option, not just an acceptable one"],
        "limitations": ["Weights are fixed: the same trade-off is used in calm and in urgent situations", "The deadline is not an explicit constraint: a cheap route can win even when it will be late", "Weights must be tuned by hand"],
    }
    diagram = {
        "perception": ["Traffic feeds, weather", "Route facts (km, toll)"],
        "extra": [{"label": "Model: predict outcome", "kind": "model", "lines": ["time, cost, safety per route"]},
                  {"label": "Utility function", "kind": "utility", "lines": ["U = .40T + .30S + .20C + .10D", "scores 0-100"]}],
        "decision": ["Score every route", "Choose max utility"],
        "action": ["Ride chosen route"],
        "environment": ["City roads, traffic, weather"],
        "feedback": "new percepts",
    }

    def __init__(self) -> None:
        super().__init__()
        self.percepts: List[Percept] = []

    def reset(self) -> None:
        super().reset()
        self.percepts = []

    def perceive(self, p: Percept) -> None:
        self.percepts.append(p)
        self.trace.add("observe", f"Percept @{p.clock}",
                       f"Weather {p.weather}; traffic " + ", ".join(f"{r}={v or 'no report'}" for r, v in p.reports.items()) + ".",
                       kind="percept", data={"weather": p.weather, "reports": p.reports})

    def decide(self) -> Decision:
        p = self.percepts[-1]
        lv = {r: k["level"] for r, k in latest_known(self.percepts).items()}
        prep, deadline = p.order.prep_min, p.order.deadline_min
        routes = by_distance(p)
        est = {r: predict(r, lv, p) for r in routes}
        best_t = min(e.travel_min for e in est.values())
        best_c = min(e.cost for e in est.values())
        best_d = min(e.distance_km for e in est.values())
        self.trace.add("reason", "Predict every route",
                       "Using the latest known traffic (" + ", ".join(f"{r}: {lv[r] or 'unknown->normal'}" for r in routes) +
                       f"). Best values: time {best_t:.1f} min, cost {best_c:.2f} CU, distance {best_d:.1f} km.",
                       kind="table", data={"rows": [{"route": r, "travel": round(e.travel_min, 1), "cost": round(e.cost, 2),
                                                     "safety": round(e.safety, 2), "km": round(e.distance_km, 2)} for r, e in est.items()]},
                       focus=routes, marks={r: "checking" for r in routes})
        rows = []
        for r in routes:
            e = est[r]
            s = {"time": 100 * best_t / e.travel_min, "safety": 100 * e.safety,
                 "cost": 100 * best_c / e.cost, "distance": 100 * best_d / e.distance_km}
            contrib = {k: WEIGHTS[k] * v for k, v in s.items()}
            rows.append({"route": r, "travel": round(e.travel_min, 1), "arrival": round(prep + e.travel_min, 1),
                         "cost": round(e.cost, 2), "safety": round(e.safety, 2), "km": round(e.distance_km, 2),
                         "scores": {k: round(v, 1) for k, v in s.items()},
                         "contrib": {k: round(v, 2) for k, v in contrib.items()},
                         "utility": round(sum(contrib.values()), 2)})
            last = rows[-1]
            self.trace.add("reason", f"Utility of route {r} = {last['utility']:.1f}",
                           " + ".join(f"{WEIGHTS[k]:.2f}×{last['scores'][k]:.0f}" for k in WEIGHTS) + f" = {last['utility']:.1f}  "
                           f"(Time {last['scores']['time']:.0f}, Safety {last['scores']['safety']:.0f}, Cost {last['scores']['cost']:.0f}, Distance {last['scores']['distance']:.0f}).",
                           kind="utility", data={"rows": [dict(x) for x in rows], "weights": WEIGHTS}, focus=[r], marks={r: "checking"})
        best = max(rows, key=lambda x: x["utility"])
        ranked = sorted(rows, key=lambda x: -x["utility"])
        late = best["arrival"] > deadline
        why = (f"Route {best['route']} gets the best overall score ({best['utility']:.1f} out of 100) when time, safety, cost and "
               f"distance are combined; the runner-up is route {ranked[1]['route']} ({ranked[1]['utility']:.1f})")
        self.trace.add("decide", f"Action: take route {best['route']} (max utility)",
                       why[0].upper() + why[1:] + f". Predicted arrival {best['arrival']} min vs deadline {deadline:g}"
                       + (" - it will probably be LATE, but the fixed weights do not treat the deadline as a constraint." if late else "."),
                       kind="utility", data={"rows": rows, "weights": WEIGHTS, "chosen": best["route"]},
                       focus=[best["route"]], marks={x["route"]: ("chosen" if x is best else "candidate") for x in rows})
        self.use("U1", "U2", "U3", "U4", "U5", "U6", "U7")
        names = {"time": "time", "safety": "safety", "cost": "cost", "distance": "distance"}
        for x in rows:
            if x is best:
                self.note(x["route"], "chosen", f"It has the best overall score, {x['utility']:.1f} out of 100. Its marks out of 100 are: "
                                                f"time {x['scores']['time']:.0f}, safety {x['scores']['safety']:.0f}, cost {x['scores']['cost']:.0f} "
                                                f"and distance {x['scores']['distance']:.0f}."
                          + (" It is expected to miss the deadline, but this agent does not treat the deadline as a strict limit."
                             if late else ""))
                continue
            loss = {k: best["contrib"][k] - x["contrib"][k] for k in WEIGHTS}
            worst = max(loss, key=loss.get)
            better = [k for k in WEIGHTS if loss[k] < -0.05]
            text = (f"Its overall score is lower ({x['utility']:.1f} against {best['utility']:.1f} for route {best['route']}). "
                    f"It loses most on {names[worst]}, where it scores {x['scores'][worst]:.0f} out of 100 against "
                    f"{best['scores'][worst]:.0f}")
            if better:
                text += ". It is better on " + " and ".join(f"{names[k]} ({x['scores'][k]:.0f} against {best['scores'][k]:.0f})" for k in better)
                text += ", but not by enough to make up the difference"
            self.note(x["route"], "rejected", text + ".")
        return Decision(best["route"], why, predicted_total_min=best["arrival"])

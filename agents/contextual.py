"""Agent 7 - Contextual Agent.

Collects CONTEXT (weather, time of day, urgency, deadline slack, congestion, sensor
reliability, type of food), classifies the situation, and switches to the strategy
that fits that context. Unlike the utility agent (one fixed formula for every
situation) and the reflex agent (no evaluation at all), the contextual agent changes
WHAT it optimises and WHICH constraints it enforces depending on the situation.
"""
from __future__ import annotations

from typing import Dict, List

from engine.environment import Percept

from .base import Agent, Decision, by_distance, estimate_row, latest_known, predict

SPILL_SENSITIVE = ("soup", "drink", "shake", "coffee", "tea")
STALE_MARGIN = 0.10      # +10% predicted time for a route whose report is not from the latest feed

STRATEGIES = {
    "storm_urgent": {"label": "Storm + urgent", "objective": "earliest arrival", "safety_floor": 0.60,
                     "text": "Hazard and a tight deadline: enforce a minimum safety level, then arrive as early as possible; notify the customer if late."},
    "storm": {"label": "Storm", "objective": "highest safety", "safety_floor": 0.65,
              "text": "Hazardous roads, no rush: choose the safest route that is still on time."},
    "congested": {"label": "Congested", "objective": "earliest arrival (uncertainty-aware)", "safety_floor": 0.0,
                  "text": "Traffic jams: minimise arrival time, adding a margin to routes whose traffic information is old."},
    "urgent": {"label": "Urgent", "objective": "earliest arrival", "safety_floor": 0.0,
               "text": "Clear roads but an urgent order: take the fastest route."},
    "calm": {"label": "Calm", "objective": "lowest cost", "safety_floor": 0.0,
             "text": "Nothing special: take the cheapest route that arrives with at least 5 minutes to spare."},
}


class ContextualAgent(Agent):
    key = "contextual"
    name = "Contextual Agent"
    short = "Contextual"
    architecture = "Classify the situation, then switch strategy"
    color = "#ff6b9a"
    RULEBOOK = [
        {"title": "Step 1: work out what kind of situation it is (checked in this order)", "rules": [
            {"id": "C1", "text": "If it is raining and the order is urgent (or there is very little spare time), the situation is \"Storm + urgent\"."},
            {"id": "C2", "text": "If it is raining, the situation is \"Storm\"."},
            {"id": "C3", "text": "If two or more routes are jammed, or it is rush hour, the situation is \"Congested\"."},
            {"id": "C4", "text": "If the order is urgent, the situation is \"Urgent\"."},
            {"id": "C5", "text": "Otherwise the situation is \"Calm\"."},
        ]},
        {"title": "Step 2: use the strategy that suits that situation", "rules": [
            {"id": "K1", "text": "Calm: take the cheapest route that still leaves at least 5 minutes to spare."},
            {"id": "K2", "text": "Congested: take the route that arrives first. Routes whose traffic information is old are treated as 10% slower, to be safe."},
            {"id": "K3", "text": "Urgent: take the route that arrives first."},
            {"id": "K4", "text": "Storm: ignore any route that is not safe enough, then take the safest route that still arrives on time."},
            {"id": "K5", "text": "Storm + urgent: ignore any route that is not safe enough, then take the one that arrives first. Tell the customer if it may be late."},
        ]},
        {"title": "Extra adjustments", "rules": [
            {"id": "X1", "text": "At night, the agent asks for a slightly higher level of safety."},
            {"id": "X2", "text": "If the food can spill (soup or drinks), the agent avoids flooded roads."},
            {"id": "X3", "text": "In congested traffic, routes whose traffic report is not the newest one get a 10% time margin."},
        ]},
    ]
    info = {
        "definition": "A contextual (context-aware) agent collects information about the situation it is in and adapts its decision policy to that context.",
        "principle": "collect context features -> classify the context -> select the matching strategy (objective + constraints) -> apply it.",
        "logic": "Context features: weather, night, urgency, number of heavy routes, rush hour, missing sensor reports, spill-sensitive food, deadline slack. The context is classified as Storm + urgent, Storm, Congested, Urgent or Calm. Each class has its own objective (cost, safety or arrival time) and constraints (minimum safety, +0.05 at night; spill-sensitive food avoids flooded lanes; old traffic reports get a +10% time margin).",
        "example": "Storm + urgent: safety floor 0.65 (night) removes A and C; of B and D, D arrives earliest (and on time), so D is chosen. In the calm afternoon the same agent picks the cheapest on-time route.",
        "advantages": ["Behaves differently when the situation calls for it", "Combines several decision styles in one agent", "Uses more information (time, food type, data reliability)"],
        "limitations": ["Context classes and strategies are designed by hand", "A wrongly classified context leads to the wrong strategy", "More rules to maintain and test"],
    }
    diagram = {
        "perception": ["Traffic, weather, clock", "order: urgency, food, deadline"],
        "extra": [{"label": "Context model", "kind": "context", "lines": ["features -> context class"]},
                  {"label": "Strategy library", "kind": "utility", "lines": ["calm: cheapest", "congested: fastest±margin", "storm(+urgent): safety floor"]}],
        "decision": ["Classify context", "Apply that strategy"],
        "action": ["Ride chosen route", "Notify if late"],
        "environment": ["City roads, traffic, weather"],
        "feedback": "new context",
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
                       f"Weather {p.weather}, {p.time_of_day}; traffic " + ", ".join(f"{r}={v or 'no report'}" for r, v in p.reports.items()) + ".",
                       kind="percept", data={"weather": p.weather, "reports": p.reports})

    def context(self) -> Dict:
        p = self.percepts[-1]
        known = latest_known(self.percepts)
        lv = {r: k["level"] for r, k in known.items()}
        heavy = [r for r, v in lv.items() if v == "heavy"]
        missing = [r for r, v in p.reports.items() if v is None]
        best = min(predict(r, lv, p).travel_min for r in lv)
        return {
            "weather": p.weather, "night": p.night, "time_of_day": p.time_of_day, "urgent": p.order.urgent,
            "heavy_routes": heavy, "rush_hour": "rush" in p.time_of_day, "missing_reports": missing,
            "stale": [r for r, k in known.items() if k["level"] and not k.get("latest")],
            "spill_sensitive": any(w in p.order.food.lower() for w in SPILL_SENSITIVE), "food": p.order.food,
            "slack": round(p.order.deadline_min - p.order.prep_min - best, 1), "levels": lv,
        }

    def classify(self, c: Dict) -> str:
        if c["weather"] == "rain":
            return "storm_urgent" if c["urgent"] or c["slack"] < 5 else "storm"
        if len(c["heavy_routes"]) >= 2 or c["rush_hour"]:
            return "congested"
        if c["urgent"]:
            return "urgent"
        return "calm"

    def decide(self) -> Decision:
        p = self.percepts[-1]
        o = p.order
        c = self.context()
        self.trace.add("reason", "Collect context",
                       f"weather={c['weather']}{' (night)' if c['night'] else ''}, time={c['time_of_day']}, urgent={c['urgent']}, "
                       f"heavy routes={c['heavy_routes'] or 'none'}, missing reports={c['missing_reports'] or 'none'}, "
                       f"food='{c['food']}'{' (spill-sensitive)' if c['spill_sensitive'] else ''}, best-case slack={c['slack']} min.",
                       kind="context", data={"context": c})
        cls = self.classify(c)
        self.use({"storm_urgent": "C1", "storm": "C2", "congested": "C3", "urgent": "C4", "calm": "C5"}[cls],
                 {"calm": "K1", "congested": "K2", "urgent": "K3", "storm": "K4", "storm_urgent": "K5"}[cls])
        st = dict(STRATEGIES[cls])
        if c["night"] and st["safety_floor"] > 0:
            st["safety_floor"] = round(st["safety_floor"] + 0.05, 2)
            self.use("X1")
        if c["spill_sensitive"]:
            self.use("X2")
        self.trace.add("reason", f"Context class: {st['label']}",
                       f"Strategy -> objective: {st['objective']}; minimum safety {st['safety_floor']:.2f}"
                       + (" (+0.05 because it is night)" if c["night"] and st["safety_floor"] > 0 else "") + f". {st['text']}",
                       kind="context", data={"context": c, "class": cls, "strategy": st})
        routes = by_distance(p)
        rows = {}
        for r in routes:
            row = estimate_row(predict(r, c["levels"], p), o.prep_min, o.deadline_min)
            if r in c["stale"] and cls == "congested":
                extra = (row["travel"]) * STALE_MARGIN
                row["arrival_adj"] = round(row["arrival"] + extra, 1)
                row["note"] = f"old report +{extra:.1f} min"
                self.use("X3")
            else:
                row["arrival_adj"] = row["arrival"]
            rows[r] = row
        excluded = {}
        for r in routes:
            if rows[r]["safety"] < st["safety_floor"]:
                excluded[r] = f"it is not safe enough (safety {rows[r]['safety']:.2f}, but at least {st['safety_floor']:.2f} is required)"
            elif c["spill_sensitive"] and rows[r]["flooded"]:
                excluded[r] = "the road is flooded and the food could spill"
        allowed = [r for r in routes if r not in excluded] or routes
        self.trace.add("reason", "Apply the strategy's constraints",
                       ("Excluded: " + "; ".join(f"{r} ({why})" for r, why in excluded.items()) if excluded else "No route excluded")
                       + f". Remaining: {', '.join(allowed)}.", kind="table",
                       data={"rows": list(rows.values()), "excluded": excluded, "class": cls},
                       focus=allowed, marks={r: ("rejected" if r in excluded else "candidate") for r in routes})
        notify = False
        if cls == "calm":
            pool = [r for r in allowed if rows[r]["slack"] >= 5] or allowed
            choice = min(pool, key=lambda r: rows[r]["cost"])
            why = (f"The situation is calm, so the agent saves money: route {choice} is the cheapest route that still leaves at least "
                   f"5 minutes to spare ({rows[choice]['cost']:.2f} cost units, about {rows[choice]['slack']:g} minutes to spare)")
        elif cls == "storm":
            pool = [r for r in allowed if rows[r]["slack"] >= 0] or allowed
            choice = max(pool, key=lambda r: rows[r]["safety"])
            why = (f"There is a storm, so the agent puts safety first: route {choice} is the safest route that still arrives on time "
                   f"(safety {rows[choice]['safety']:.2f})")
        else:
            choice = min(allowed, key=lambda r: rows[r]["arrival_adj"])
            notify = rows[choice]["arrival"] > o.deadline_min
            lead = {"congested": "Traffic is heavy, so the agent's priority is to arrive as early as possible",
                    "urgent": "The order is urgent, so the agent's priority is to arrive as early as possible",
                    "storm_urgent": "There is a storm and the order is urgent, so the agent first rules out unsafe roads and then picks "
                                    "the one that arrives earliest"}[cls]
            why = (f"{lead}: route {choice} should arrive first, after about {rows[choice]['arrival_adj']} minutes"
                   + (" (including a safety margin because its traffic information is old)" if rows[choice]['arrival_adj'] != rows[choice]['arrival'] else ""))
            if notify:
                why += ". It may still be late, so the customer is told"
        c0 = rows[choice]
        for r in routes:
            x = rows[r]
            if r == choice:
                self.note(r, "chosen", why[0].upper() + why[1:] + ".")
            elif r in excluded:
                self.note(r, "rejected", f"Ruled out in this \"{st['label']}\" situation because {excluded[r]}.")
            elif cls == "calm":
                self.note(r, "rejected", f"It would leave less than 5 minutes to spare (about {x['slack']:g} minutes)." if x["slack"] < 5 <= c0["slack"]
                          else f"In a calm situation the agent picks the cheapest route, and this one costs more "
                               f"({x['cost']:.2f} against {c0['cost']:.2f} cost units).")
            elif cls == "storm":
                self.note(r, "rejected", f"It would arrive late (about {-x['slack']:g} minutes after the deadline)." if x["slack"] < 0 <= c0["slack"]
                          else f"In a storm the agent picks the safest route, and this one is less safe "
                               f"({x['safety']:.2f} against {c0['safety']:.2f}).")
            else:
                self.note(r, "rejected", f"It would arrive later than route {choice} (about {x['arrival_adj']} minutes against "
                                         f"{c0['arrival_adj']}" + (", including a safety margin because its traffic information is old"
                                                                    if x.get("note") else "") + ").")
        self.trace.add("decide", f"Action: take route {choice}" + (" + notify customer" if notify else ""),
                       why[0].upper() + why[1:] + ".", kind="decision",
                       data={"rows": list(rows.values()), "class": cls, "route": choice}, focus=[choice], marks={choice: "chosen"})
        return Decision(choice, why, notify_customer=notify, predicted_total_min=rows[choice]["arrival"])

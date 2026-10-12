"""Agent 2 - Model-Based Reflex Agent.

Keeps an INTERNAL STATE of the world (traffic per route with the time it was seen,
weather, flooded roads, order status, current route). Each percept updates the state
through a transition model; when a sensor is offline the last known value is kept
(and ages). Condition-action rules are then applied to the state, not to the raw percept.
"""
from __future__ import annotations

import copy
from typing import Dict

from engine.environment import Percept

from .base import Agent, Decision, by_distance, estimate_row, predict

STALE_AFTER_MIN = 30   # a remembered report older than this is no longer trusted


def _clock_min(clock: str) -> int:
    h, m = clock.split(":")
    return int(h) * 60 + int(m)


class ModelBasedReflexAgent(Agent):
    key = "model_based"
    name = "Model-Based Reflex Agent"
    short = "Model-Based"
    architecture = "Rules applied to a remembered internal world state"
    color = "#f78c1f"
    RULES = [
        ("M1", "IF the usual route is believed light/normal AND not flooded", "THEN take the usual route"),
        ("M2", "IF the usual route is believed heavy OR flooded", "THEN take the clear (not heavy, not flooded) route with the lowest predicted arrival"),
        ("M3", "IF every route is heavy or flooded", "THEN take the route with the lowest predicted arrival"),
    ]
    RULEBOOK = [
        {"title": "How the agent updates its memory (internal state) each time a traffic report arrives", "rules": [
            {"id": "S1", "text": "When a road is reported, the agent writes down its traffic level and the time it was seen."},
            {"id": "S2", "text": "When a road is missing from the report, the agent keeps what it remembered about that road, as long as the memory is no more than 30 minutes old."},
            {"id": "S3", "text": "If what it remembers about a road is more than 30 minutes old, the agent forgets it and treats the road as unknown."},
            {"id": "S4", "text": "When it is raining, the agent marks roads that tend to flood as flooded."},
        ]},
        {"title": "How the agent decides, using its memory (checked in this order)", "rules": [
            {"id": "M1", "text": "If it believes the usual (shortest) route is clear and not flooded, it takes the usual route."},
            {"id": "M2", "text": "If it believes the usual route is jammed or flooded, it looks at the routes it believes are clear and takes the one it expects to arrive first."},
            {"id": "M3", "text": "If it believes every route is jammed or flooded, it takes whichever route it expects to arrive first."},
        ]},
    ]
    info = {
        "definition": "A model-based reflex agent keeps an internal state that summarises the parts of the world it cannot see right now, and applies condition-action rules to that state.",
        "principle": "state <- update(state, percept, model of how the world changes); action <- rule(state).",
        "logic": "Each percept updates the belief about every route's traffic (with the clock time it was observed). A missing report keeps the previous belief, which ages and is dropped after 30 minutes. The transition model marks flood-prone roads as flooded when it rains. Rules M1-M3 run on this state; M2/M3 use the internal model to predict arrival times.",
        "example": "Rush hour: the ring road (B) sensor is offline now, but the state still holds 'B light, seen 10 min ago', so the agent picks B, which the simple reflex agent could not see.",
        "advantages": ["Copes with partial observability (missing or delayed sensor data)", "Still rule-based, so it is fast and explainable", "Models effects such as flooding that are not reported directly"],
        "limitations": ["Remembered information can be stale or wrong", "Rules are hand-written; no explicit goal or trade-off between cost and safety", "Quality depends on the accuracy of the internal model"],
    }
    diagram = {
        "perception": ["Traffic feeds (may be partial)", "Weather, order"],
        "extra": [{"label": "Internal state", "kind": "state", "lines": ["route traffic + time seen", "flooded roads", "order status, current route"]},
                  {"label": "Model: how the world evolves", "kind": "model", "lines": ["missing report -> keep & age", "rain -> flood-prone roads flood"]}],
        "decision": ["Rules M1-M3 on the state"],
        "action": ["Ride chosen route"],
        "environment": ["City roads, traffic, weather"],
        "feedback": "percept updates the state",
    }

    def __init__(self) -> None:
        super().__init__()
        self.reset()

    def reset(self) -> None:
        super().reset()
        self.state: Dict = {"clock": None, "weather": None, "traffic": {}, "flooded": [],
                            "order_status": "no order", "current_route": None, "order": None}
        self._percept = None

    # ------------------------------------------------------------------ state update
    def perceive(self, p: Percept) -> None:
        before = copy.deepcopy(self.state)
        now = _clock_min(p.clock) if ":" in p.clock else p.minute
        changes = []
        for rid, lvl in p.reports.items():
            old = self.state["traffic"].get(rid)
            if lvl is not None:
                self.use("S1")
                self.state["traffic"][rid] = {"level": lvl, "seen": p.clock, "age": 0, "source": "observed"}
                if not old or old["level"] != lvl:
                    changes.append(f"{rid}: {old['level'] if old else 'unknown'} -> {lvl} (observed)")
            elif old:
                age = now - (_clock_min(old["seen"]) if ":" in str(old["seen"]) else 0)
                if age > STALE_AFTER_MIN:
                    self.use("S3")
                    self.state["traffic"][rid] = {"level": None, "seen": old["seen"], "age": age, "source": "too old"}
                    changes.append(f"{rid}: memory from {old['seen']} is {age} min old -> forgotten")
                else:
                    self.use("S2")
                    self.state["traffic"][rid] = {**old, "age": age, "source": "remembered"}
                    changes.append(f"{rid}: no report -> keep remembered '{old['level']}' from {old['seen']} ({age} min old)")
            else:
                self.state["traffic"][rid] = {"level": None, "seen": None, "age": None, "source": "unknown"}
                changes.append(f"{rid}: no report and nothing remembered -> unknown")
        if self.state["weather"] != p.weather:
            changes.append(f"weather: {self.state['weather'] or 'unknown'} -> {p.weather}")
        self.state["weather"] = p.weather
        flooded = [r for r, f in p.routes.items() if f["flood_prone"] and p.weather == "rain"]
        if flooded:
            self.use("S4")
        if flooded != self.state["flooded"]:
            changes.append(f"model: rain + flood-prone road -> {', '.join(flooded)} flooded" if flooded else "model: no flooding")
        self.state["flooded"] = flooded
        self.state["clock"] = p.clock
        self.state["order"] = {"id": p.order.order_id, "deadline_min": p.order.deadline_min, "urgent": p.order.urgent}
        self.state["order_status"] = "accepted, awaiting pickup"
        self._percept = p
        self.trace.add("observe", f"Percept @{p.clock} -> update internal state",
                       "Changes: " + ("; ".join(changes) if changes else "none") + ".", kind="state",
                       data={"previous": before, "observation": {"weather": p.weather, "reports": p.reports},
                             "updated": copy.deepcopy(self.state), "changes": changes},
                       focus=[r for r in p.reports if p.reports[r] or r in flooded])

    def believed(self) -> Dict[str, str]:
        return {r: v["level"] for r, v in self.state["traffic"].items()}

    # ------------------------------------------------------------------ rules on the state
    def decide(self) -> Decision:
        p = self._percept
        lv = self.believed()
        flooded = set(self.state["flooded"])
        order = by_distance(p)
        usual = order[0]
        rules = [{"id": r[0], "if": r[1], "then": r[2], "status": "not checked"} for r in self.RULES]
        prep, deadline = p.order.prep_min, p.order.deadline_min
        state_view = {r: f"{lv[r] or 'unknown'}{' (flooded)' if r in flooded else ''}" for r in order}
        self.trace.add("reason", "Read the internal state",
                       "Believed traffic: " + ", ".join(f"{r} {v}" for r, v in state_view.items()) + ".",
                       kind="state", data={"state": state_view, "rules": [dict(x) for x in rules]})

        if lv[usual] in ("light", "normal") and usual not in flooded:
            rules[0]["status"] = "fired"
            for x in rules[1:]:
                x["status"] = "skipped"
            why = (f"The agent's memory says the usual (shortest) route, {usual}, has {lv[usual]} traffic and is not flooded, "
                   f"so it takes it (rule M1)")
            self.trace.add("reason", f"M1 fires: usual route {usual} is clear", why + ".", kind="rule",
                           data={"rules": rules}, focus=[usual], marks={usual: "chosen"})
            choice = usual
            est = predict(usual, lv, p)
        else:
            rules[0]["status"] = "false"
            problem = "flooded" if usual in flooded else f"believed {lv[usual] or 'unknown'}"
            clear = [r for r in order if lv[r] in ("light", "normal") and r not in flooded]
            rows = [estimate_row(predict(r, lv, p), prep, deadline) for r in order]
            idx = {row["route"]: row for row in rows}
            if clear:
                rules[1]["status"], rules[2]["status"] = "fired", "skipped"
                choice = min(clear, key=lambda r: idx[r]["arrival"])
                why = (f"The agent's memory says the usual route, {usual}, is {'flooded' if usual in flooded else 'jammed'}. "
                       f"Of the routes it believes are clear ({', '.join(clear)}), route {choice} should arrive first, "
                       f"after about {idx[choice]['arrival']} minutes (rule M2)")
                title = f"M2 fires: route {choice} is the fastest clear route"
            else:
                rules[1]["status"], rules[2]["status"] = "false", "fired"
                choice = min(order, key=lambda r: idx[r]["arrival"])
                why = (f"The agent believes every route is jammed or flooded, so it takes route {choice}, which should arrive "
                       f"first, after about {idx[choice]['arrival']} minutes (rule M3)")
                title = f"M3 fires: least-bad route {choice}"
            marks = {r: ("chosen" if r == choice else "candidate" if r in clear else "rejected") for r in order}
            self.trace.add("reason", f"Usual route {usual} is {problem}: rule M1 fails",
                           f"Routes believed clear (not heavy, not flooded): {', '.join(clear) or 'none'}. "
                           "The internal model predicts their arrival times.", kind="table",
                           data={"rows": rows, "clear": clear, "rules": rules}, focus=clear,
                           marks={r: ("candidate" if r in clear else "rejected") for r in order})
            self.trace.add("reason", title, why + ".", kind="rule", data={"rules": rules}, focus=[choice], marks=marks)
            est = predict(choice, lv, p)
        for r in order:
            seen = self.state["traffic"].get(r, {}).get("seen")
            if r == choice:
                self.note(r, "chosen", why + ".")
            elif r in flooded:
                self.note(r, "rejected", "It is raining and this road floods, so the agent's memory marks it as flooded and it is avoided.")
            elif lv[r] == "heavy":
                self.note(r, "rejected", f"The agent remembers heavy traffic on this route (from the report at {seen}), so it avoided it.")
            elif lv[r] is None:
                self.note(r, "rejected", "The agent has no information about this route in its memory, so it did not treat it as clear.")
            elif rules[0]["status"] == "fired":
                self.note(r, "not considered", f"The usual route {choice} was clear, so the agent took it without needing to look at the other routes.")
            else:
                self.note(r, "rejected", f"The agent believes this route is clear ({lv[r]} traffic, seen at {seen}), but expects it to arrive "
                                         f"after about {idx[r]['arrival']} minutes, later than route {choice} (about {idx[choice]['arrival']} minutes).")
        self.use(*[x["id"] for x in rules if x["status"] == "fired"])
        self.state["current_route"] = choice
        self.state["order_status"] = "route chosen"
        self.trace.add("decide", f"Action: take route {choice}", why + ".", kind="decision",
                       data={"route": choice, "state": copy.deepcopy(self.state)}, focus=[choice], marks={choice: "chosen"})
        return Decision(choice, why, predicted_total_min=prep + est.travel_min)

    def on_execution(self, stage: str, info: dict) -> None:
        self.state["order_status"] = {"pickup": "food picked up", "ride": "en route", "delivered": "delivered"}[stage]

    def snapshot(self) -> dict:
        return {"state": copy.deepcopy(self.state)}

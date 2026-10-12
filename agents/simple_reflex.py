"""Agent 1 - Simple Reflex Agent.

Acts on the CURRENT percept only, using fixed condition-action (IF-THEN) rules.
It keeps no memory: when a new percept arrives the previous one is discarded, so a
road whose sensor is offline right now is invisible to it.
"""
from __future__ import annotations

from typing import Optional

from engine.environment import Percept

from .base import Agent, Decision, by_distance, fmt_levels

OK_LEVELS = ("light", "normal")


class SimpleReflexAgent(Agent):
    key = "simple_reflex"
    name = "Simple Reflex Agent"
    short = "Simple Reflex"
    architecture = "Condition-action rules on the current percept"
    color = "#ef476f"
    RULES = [
        ("R1", "IF it is raining", "THEN remove flood-prone routes from consideration"),
        ("R2", "IF the usual (shortest) route's traffic is light or normal", "THEN take the usual route"),
        ("R3", "IF the usual route's traffic is heavy", "THEN take the first alternative (by distance) reported light or normal"),
        ("R4", "IF no other rule selected a route", "THEN take the usual route"),
    ]
    RULEBOOK = [
        {"title": "The agent's four rules, checked in this order. The first rule that picks a route decides.", "rules": [
            {"id": "R1", "text": "When it is raining, the agent removes any route that floods (the Old Town Lanes) from its list."},
            {"id": "R2", "text": "If the usual route (the shortest one left) has light or normal traffic, the agent simply takes it."},
            {"id": "R3", "text": "If the usual route has heavy traffic, the agent takes the next shortest route that is reported to have light or normal traffic."},
            {"id": "R4", "text": "If none of the rules above picked a route, the agent takes the usual route anyway."},
        ]},
        {"title": "How it sees the world (it has no memory)", "rules": [
            {"id": "P", "text": "The agent only looks at the newest traffic report. As soon as a new report arrives, it forgets the old one."},
            {"id": "U", "text": "If a road's traffic sensor is offline in the newest report, the agent cannot see that road at all, so it can never choose it."},
        ]},
    ]
    info = {
        "definition": "A simple reflex agent selects an action using only the current percept and a fixed set of condition-action (IF-THEN) rules.",
        "principle": "percept -> match the first rule whose condition is true -> do that rule's action. There is no memory, no prediction and no evaluation of outcomes.",
        "logic": "Routes are ordered by distance; the shortest allowed route is the 'usual' route. The four rules R1-R4 are checked in order against the latest traffic feed and the weather. A route with no report in the latest feed cannot satisfy any rule, because the agent does not remember earlier feeds.",
        "example": "Rush hour: the usual route A is reported heavy, so R3 fires. Route B's sensor is offline, so the agent cannot see that B is light; it takes C, the first alternative reported normal.",
        "advantages": ["Very fast and easy to explain", "Predictable: same percept -> same action", "Needs no model, training or data"],
        "limitations": ["Blind to anything not in the current percept (missing sensor data)", "Never checks the deadline, cost or safety", "Rules must be written by hand and cannot adapt"],
    }
    diagram = {
        "perception": ["Current traffic feed only", "Weather now"],
        "extra": [{"label": "Condition-action rules", "kind": "rules", "lines": ["R1 rain -> avoid flood-prone", "R2 usual OK -> usual", "R3 usual heavy -> alternative", "R4 default -> usual"]}],
        "decision": ["Match first true rule"],
        "action": ["Ride chosen route"],
        "environment": ["City roads, traffic, weather"],
        "feedback": "next percept (previous one is forgotten)",
    }

    def reset(self) -> None:
        super().reset()
        self.percept: Optional[Percept] = None

    def __init__(self) -> None:
        super().__init__()
        self.percept = None

    def perceive(self, percept: Percept) -> None:
        if self.percept is not None:
            self.trace.add("observe", f"Percept @{self.percept.clock} discarded",
                           f"A new percept arrived, so the reading from {self.percept.clock} "
                           f"({fmt_levels(self.percept.reports)}) is thrown away. A simple reflex agent has no memory.",
                           kind="forget", data={"forgotten": self.percept.reports})
        self.percept = percept           # overwrite: the only thing the agent knows
        self.trace.add("observe", f"Percept @{percept.clock}",
                       f"Weather: {percept.weather}. Traffic feed: {fmt_levels(percept.reports)}.",
                       kind="percept", data={"weather": percept.weather, "reports": percept.reports},
                       focus=[r for r, v in percept.reports.items() if v])

    def decide(self) -> Decision:
        p = self.percept
        rep = p.reports
        rules = [{"id": r[0], "if": r[1], "then": r[2], "status": "not checked"} for r in self.RULES]
        order = by_distance(p)
        allowed = list(order)

        def show(i: int, status: str, title: str, text: str, focus=None, marks=None):
            rules[i]["status"] = status
            self.trace.add("reason", title, text, kind="rule",
                           data={"rules": [dict(x) for x in rules], "allowed": list(allowed)},
                           focus=focus, marks=marks)

        # R1 - weather filter
        if p.weather == "rain":
            removed = [r for r in allowed if p.routes[r]["flood_prone"]]
            allowed = [r for r in allowed if not p.routes[r]["flood_prone"]]
            show(0, "fired", "R1 fires: it is raining",
                 f"Condition true (weather = rain). Flood-prone route(s) {', '.join(removed) or 'none'} removed. "
                 f"Remaining: {', '.join(allowed)}.", focus=removed, marks={r: "rejected" for r in removed})
        else:
            show(0, "false", "R1 does not match", "Condition false (weather = clear), so no route is removed.")

        usual = allowed[0]
        lvl = rep.get(usual)
        choice, why, fired = None, "", None
        # R2
        if lvl in OK_LEVELS:
            choice, fired = usual, 1
            why = f"The usual (shortest) route, {usual}, has {lvl} traffic, so the agent simply takes it (rule R2)"
            show(1, "fired", f"R2 fires: usual route {usual} is {lvl}",
                 f"Route {usual} is the shortest allowed route ({p.routes[usual]['distance_km']} km) and its current report is '{lvl}'.",
                 focus=[usual], marks={usual: "chosen"})
        else:
            show(1, "false", f"R2 does not match: route {usual} is {lvl or 'not reported'}",
                 f"The usual route {usual} is reported '{lvl or 'no report'}', which is not light or normal.",
                 focus=[usual], marks={usual: "checking"})
            # R3
            if lvl == "heavy":
                checked = []
                for alt in allowed[1:]:
                    checked.append(f"{alt}={rep.get(alt) or 'no report'}")
                    if rep.get(alt) in OK_LEVELS:
                        choice, fired = alt, 2
                        break
                if choice:
                    why = (f"The usual route, {usual}, is jammed, so the agent takes the next shortest route it can see with acceptable "
                           f"traffic: route {choice}, which has {rep[choice]} traffic (rule R3)")
                    blind = [r for r in allowed[1:] if rep.get(r) is None]
                    show(2, "fired", f"R3 fires: switch to route {choice}",
                         f"Alternatives checked in distance order: {', '.join(checked)}. Route {choice} is the first one "
                         f"reported light or normal." + (f" Route(s) {', '.join(blind)} had no report, so the agent cannot consider them." if blind else ""),
                         focus=[choice], marks={usual: "rejected", choice: "chosen", **{b: "unknown" for b in blind}})
                else:
                    show(2, "false", "R3 matches but finds no alternative",
                         f"No alternative is reported light or normal ({', '.join(checked)}).", marks={usual: "checking"})
            else:
                show(2, "false", "R3 does not match", f"The usual route is not reported heavy ({lvl or 'no report'}).")
        if choice is None:
            choice, fired = usual, 3
            why = f"No other rule picked a route, so the agent falls back to the usual route, {usual} (rule R4)"
            show(3, "fired", f"R4 fires: default to usual route {usual}", "No earlier rule selected a route.",
                 focus=[usual], marks={usual: "chosen"})
        for i in range(fired + 1, len(rules)):
            rules[i]["status"] = "skipped"
        self.trace.add("decide", f"Action: take route {choice}", why + ". No time, cost or safety was calculated.",
                       kind="decision", data={"rules": rules, "route": choice}, focus=[choice], marks={choice: "chosen"})
        self.use("P", *[x["id"] for x in rules if x["status"] == "fired"])
        if any(rep.get(r) is None for r in order):
            self.use("U")
        removed = set(order) - set(allowed)
        for r in order:
            if r == choice:
                self.note(r, "chosen", why + ". It did not compare travel time, cost or safety with the other routes.")
            elif r in removed:
                self.note(r, "rejected", "It is raining and this road floods, so the agent crossed it off its list straight away (rule R1).")
            elif rep.get(r) is None:
                self.note(r, "rejected", "This road's traffic sensor was offline in the newest report. The agent has no memory of the earlier "
                                         "report, so it could not see this road at all and could not choose it.")
            elif r == usual:
                self.note(r, "rejected", f"This is the usual, shortest route, but it has {rep[r]} traffic, so the agent did not take it.")
            elif fired in (1, 3):
                self.note(r, "not considered", f"The agent never looked at this route. It had {rep[r]} traffic, but the agent had already "
                                               f"picked route {choice} with its first matching rule, and a simple reflex agent stops there "
                                               "without comparing the alternatives.")
            elif rep[r] == "heavy":
                self.note(r, "rejected", "This route has heavy traffic, and the agent only switches to routes with light or normal traffic.")
            else:
                self.note(r, "not considered", f"This route had {rep[r]} traffic and would have been acceptable, but the agent takes the "
                                               f"first acceptable route in order of length, and route {choice} is shorter "
                                               f"({p.routes[choice]['distance_km']} km against {p.routes[r]['distance_km']} km). "
                                               "It never compared their times, costs or safety.")
        return Decision(choice, why)

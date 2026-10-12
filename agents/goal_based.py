"""Agent 3 - Goal-Based Agent.

Has an explicit GOAL: deliver the order no later than the customer's deadline.
It generates candidate plans, predicts the result of each plan with its world
model, and tests whether the predicted result satisfies the goal. It takes the
first plan (in search order: shortest first) that passes the goal test. If no plan
can reach the goal it says so, falls back to the plan that misses it by the least,
and notifies the customer.
"""
from __future__ import annotations

from typing import List

from engine.environment import Percept

from .base import Agent, Decision, by_distance, estimate_row, latest_known, predict


class GoalBasedAgent(Agent):
    key = "goal_based"
    name = "Goal-Based Agent"
    short = "Goal-Based"
    architecture = "Predict each plan and test it against the goal"
    color = "#ffc233"
    RULEBOOK = [
        {"title": "The goal", "rules": [
            {"id": "G1", "text": "The goal is to get the food to the customer before the deadline (cooking time plus riding time must fit within the deadline)."},
        ]},
        {"title": "How it predicts each route", "rules": [
            {"id": "P1", "text": "It estimates each route's arrival time from the latest traffic it knows about, the weather, flooding and traffic lights. If a road has no recent report, it uses the earlier report; if it knows nothing, it assumes normal traffic."},
        ]},
        {"title": "How it chooses", "rules": [
            {"id": "G2", "text": "It checks the routes one by one, starting with the shortest."},
            {"id": "G3", "text": "As soon as it finds a route that will arrive before the deadline, it takes that route and stops looking. It does not search for an even better one."},
            {"id": "G4", "text": "If no route can arrive before the deadline, it admits the goal cannot be met, takes the route that will be least late and tells the customer."},
        ]},
    ]
    info = {
        "definition": "A goal-based agent chooses actions that achieve an explicit goal, by predicting what each action will lead to and checking the goal condition.",
        "principle": "for each plan: predict outcome with the model -> goal test (arrival <= deadline). Take a plan that satisfies the goal.",
        "logic": "Goal: predicted arrival (food preparation + travel) must be within the deadline. Plans are searched in order of distance (shortest first). The first plan whose prediction passes the goal test is selected. The agent does not try to find the BEST plan, only one that satisfies the goal. If none passes, the goal is declared unachievable: it chooses the plan with the smallest lateness and notifies the customer.",
        "example": "Rush hour, deadline 30 min: route A is predicted at 31.1 min (fails), route C at 24.5 min (passes), so it takes C even though B would be faster.",
        "advantages": ["Explicit about what it is trying to achieve", "Flexible: change the goal and the behaviour changes", "Detects when the goal is impossible and reacts (fallback + notify)"],
        "limitations": ["Satisficing: any plan that meets the goal is accepted, even a worse one", "Ignores cost and safety unless they are part of the goal", "Depends on the accuracy of its predictions"],
    }
    diagram = {
        "perception": ["Traffic feeds, weather", "Order deadline"],
        "extra": [{"label": "Goal", "kind": "goal", "lines": ["arrival <= deadline"]},
                  {"label": "Model: predict each plan", "kind": "model", "lines": ["time = prep + travel(traffic, rain)"]}],
        "decision": ["Search plans (shortest first)", "Goal test -> first plan that passes"],
        "action": ["Ride chosen route", "Notify if goal impossible"],
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
        known = latest_known(self.percepts)
        lv = {r: k["level"] for r, k in known.items()}
        prep, deadline = p.order.prep_min, p.order.deadline_min
        self.trace.add("reason", "Set the goal",
                       f"Goal: deliver order {p.order.order_id} within {deadline:g} min of ordering. "
                       f"Food needs {prep:g} min, so the ride must take at most {deadline - prep:g} min.",
                       kind="goal", data={"deadline": deadline, "prep": prep, "budget": deadline - prep,
                                          "beliefs": {r: (f"{k['level']} @{k['seen']}" if k['level'] else "unknown -> assume normal") for r, k in known.items()}})
        rows = []
        chosen = None
        for rid in by_distance(p):
            row = estimate_row(predict(rid, lv, p), prep, deadline)
            row["goal"] = row["arrival"] <= deadline
            rows.append(row)
            self.trace.add("reason", f"Plan {rid}: predict and test the goal",
                           f"Route {rid} ({row['km']} km): predicted arrival {row['arrival']} min vs deadline {deadline:g} -> "
                           + (f"GOAL SATISFIED ({row['slack']:+} min slack)." if row["goal"] else f"goal fails ({-row['slack']:.1f} min late)."),
                           kind="goal-test", data={"rows": [dict(r) for r in rows], "deadline": deadline},
                           focus=[rid], marks={r["route"]: ("candidate" if r["goal"] else "rejected") for r in rows})
            if row["goal"]:
                chosen = row
                break
        if chosen:
            skipped = [r for r in by_distance(p) if r not in {x["route"] for x in rows}]
            why = (f"Route {chosen['route']} is the first route the agent checked that gets the food there before the deadline "
                   f"(about {chosen['arrival']} minutes, with a {deadline:g}-minute deadline)")
            self.trace.add("decide", f"Action: take route {chosen['route']}",
                           why[0].upper() + why[1:] + ". The search stops here" +
                           (f", so route(s) {', '.join(skipped)} are never evaluated." if skipped else "."),
                           kind="decision", data={"rows": rows, "goal_achievable": True},
                           focus=[chosen["route"]], marks={chosen["route"]: "chosen"})
            self.use("G1", "P1", "G2", "G3")
            for row in rows:
                if row is chosen:
                    self.note(row["route"], "chosen", why + f". It should arrive with about {row['slack']:g} minutes to spare, so the goal is met.")
                else:
                    self.note(row["route"], "rejected", f"This route would arrive after about {row['arrival']} minutes, which is "
                                                        f"{-row['slack']:.1f} minutes after the {deadline:g}-minute deadline, so it does not meet the goal.")
            for r in skipped:
                self.note(r, "not considered", f"The agent never checked this route. It checks routes from shortest to longest and stops at the "
                                               f"first one that meets the deadline (route {chosen['route']}), even if a later route might be better.")
            return Decision(chosen["route"], why, predicted_total_min=chosen["arrival"])
        best = min(rows, key=lambda r: r["arrival"])
        why = (f"No route can get the food there before the deadline, so the agent takes route {best['route']}, which will be the "
               f"least late (about {best['arrival'] - deadline:.1f} minutes), and tells the customer")
        self.trace.add("reason", "Goal is NOT achievable",
                       f"Every plan's predicted arrival is after the {deadline:g}-min deadline. Fallback: minimise lateness.",
                       kind="goal-fail", data={"rows": rows}, marks={r["route"]: "rejected" for r in rows})
        self.trace.add("decide", f"Action: take route {best['route']} + notify customer", why[0].upper() + why[1:] + ".",
                       kind="decision", data={"rows": rows, "goal_achievable": False},
                       focus=[best["route"]], marks={best["route"]: "chosen"})
        self.use("G1", "P1", "G2", "G4")
        for row in rows:
            if row is best:
                self.note(row["route"], "chosen", f"No route can meet the deadline. This one will be the least late (about {row['arrival']} "
                                                  "minutes), so the agent takes it and tells the customer.")
            else:
                self.note(row["route"], "rejected", f"This route also misses the deadline and would be even later (about {row['arrival']} "
                                                    f"minutes instead of {best['arrival']}).")
        return Decision(best["route"], why, notify_customer=True, predicted_total_min=best["arrival"])

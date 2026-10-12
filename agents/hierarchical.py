"""Agent 6 - Hierarchical Agent.

Breaks the main goal "Deliver food" into subtasks with dependencies:

    Deliver food
    ├── 1 Accept order
    ├── 2 Check order information      (needs 1)
    ├── 3 Evaluate traffic             (needs 2)
    ├── 4 Check weather                (needs 2)
    ├── 5 Select route                 (needs 3, 4)   <- uses the results of 3 and 4
    ├── 6 Pick up food                 (needs 5)
    ├── 7 Execute delivery             (needs 6)
    └── 8 Confirm delivery             (needs 7)

A small scheduler runs whichever task has all its dependencies completed. Each task
moves pending -> running -> completed, and passes its result to later tasks through
a shared blackboard. Tasks 1-5 run when deciding; 6-8 run while the delivery is
executed in the environment.
"""
from __future__ import annotations

import copy
from typing import Callable, Dict, List, Optional

from engine.environment import Percept

from .base import Agent, Decision, by_distance, estimate_row, latest_known, predict

TASKS = [
    ("accept", "Accept order", []),
    ("check_order", "Check order information", ["accept"]),
    ("traffic", "Evaluate traffic", ["check_order"]),
    ("weather", "Check weather", ["check_order"]),
    ("select", "Select route", ["traffic", "weather"]),
    ("pickup", "Pick up food", ["select"]),
    ("deliver", "Execute delivery", ["pickup"]),
    ("confirm", "Confirm delivery", ["deliver"]),
]
DECISION_TASKS = ["accept", "check_order", "traffic", "weather", "select"]


class HierarchicalAgent(Agent):
    key = "hierarchical"
    name = "Hierarchical Agent"
    short = "Hierarchical"
    architecture = "Goal decomposed into dependent subtasks"
    color = "#8e5cf7"
    RULEBOOK = [
        {"title": "The delivery is split into eight smaller tasks. Each task can only start when the tasks before it are finished.", "rules": [
            {"id": "T1", "text": "Accept the order."},
            {"id": "T2", "text": "Check the order: how much time is left for riding after cooking, and whether the order is urgent. (Needs task 1.)"},
            {"id": "T3", "text": "Check the traffic on every route. (Needs task 2.)"},
            {"id": "T4", "text": "Check the weather to see which routes are flooded. (Needs task 2.)"},
            {"id": "T5", "text": "Choose the route, using the results of tasks 3 and 4."},
            {"id": "T6", "text": "Pick up the food once it is ready. (Needs task 5.)"},
            {"id": "T7", "text": "Ride the chosen route. (Needs task 6.)"},
            {"id": "T8", "text": "Confirm the delivery and whether it was on time. (Needs task 7.)"},
        ]},
        {"title": "How the route is chosen inside those tasks", "rules": [
            {"id": "H1", "text": "Routes with heavy traffic are ruled out (task 3)."},
            {"id": "H2", "text": "Routes that are flooded in the rain are ruled out (task 4)."},
            {"id": "H3", "text": "If every route was ruled out, the traffic check is dropped and only flooded routes stay ruled out."},
            {"id": "H4", "text": "For a normal order, it takes the cheapest remaining route that will arrive on time."},
            {"id": "H5", "text": "For an urgent order, it takes the fastest remaining route that will arrive on time."},
            {"id": "H6", "text": "If no remaining route can arrive on time, it takes the fastest one and tells the customer the order may be late."},
        ]},
    ]
    info = {
        "definition": "A hierarchical agent decomposes a complex goal into smaller subgoals or tasks, solves each with a simpler module, and combines the results.",
        "principle": "high-level goal -> ordered subtasks with dependencies -> each subtask uses the outputs of the ones before it.",
        "logic": "Eight subtasks are scheduled by dependency (a task may start only when all its prerequisites are completed). 'Evaluate traffic' rejects routes that are heavy; 'Check weather' rejects flooded routes; 'Select route' keeps the routes that pass both checks, predicts which of them meet the deadline, and picks the cheapest of those (or the fastest when the order is urgent). If a filter removes every route, the constraint is relaxed. 'Pick up', 'Execute' and 'Confirm' run during the delivery.",
        "example": "Storm: Evaluate traffic rejects A (heavy); Check weather rejects C (flooded); Select route finds that only D of the remaining {B, D} meets the deadline, so D is chosen.",
        "advantages": ["Complex behaviour from simple, testable modules", "Easy to monitor progress (task status)", "Modules can be replaced or improved separately"],
        "limitations": ["Fixed decomposition: a hard filter can throw away a good option", "More structure and overhead than a single rule", "Errors in an early subtask propagate to later ones"],
    }
    diagram = {
        "perception": ["Order, traffic feeds", "Weather"],
        "extra": [{"label": "Goal: deliver food", "kind": "goal", "lines": ["subtasks 1-8 with dependencies"]},
                  {"label": "Subtask modules", "kind": "subgoals", "lines": ["accept → check → traffic | weather", "→ select → pick up → deliver → confirm"]}],
        "decision": ["Scheduler runs ready tasks", "Select-route module decides"],
        "action": ["Pick up, ride, confirm"],
        "environment": ["City roads, traffic, weather"],
        "feedback": "task status updates",
    }

    def __init__(self) -> None:
        super().__init__()
        self.reset()

    def reset(self) -> None:
        super().reset()
        self.percepts: List[Percept] = []
        self.tasks: Dict[str, dict] = {k: {"id": k, "name": n, "deps": d, "status": "pending", "result": ""}
                                       for k, n, d in TASKS}
        self.board: Dict = {}
        self.log: List[str] = []

    # ------------------------------------------------------------------ scheduler
    def ready(self) -> List[str]:
        return [k for k, t in self.tasks.items()
                if t["status"] == "pending" and all(self.tasks[d]["status"] == "completed" for d in t["deps"])]

    def _run(self, key: str, fn: Callable[[], str], phase: str = "reason", **step) -> None:
        if key not in self.ready():
            raise RuntimeError(f"task {key} started before its dependencies completed")
        t = self.tasks[key]
        t["status"] = "running"
        self.log.append(f"{t['name']}: running")
        result = fn()
        t["status"] = "completed"
        t["result"] = result
        self.log.append(f"{t['name']}: completed")
        deps = f" (after {', '.join(self.tasks[d]['name'] for d in t['deps'])})" if t["deps"] else ""
        self.trace.add(phase, f"Subtask {[k for k, *_ in TASKS].index(key) + 1}: {t['name']}", result + deps,
                       kind="task", data={"tasks": self.task_list(), "running": key}, **step)

    def task_list(self) -> List[dict]:
        return [copy.deepcopy(self.tasks[k]) for k, *_ in TASKS]

    # ------------------------------------------------------------------ perception
    def perceive(self, p: Percept) -> None:
        self.percepts.append(p)
        self.trace.add("observe", f"Percept @{p.clock}",
                       f"Weather {p.weather}; traffic " + ", ".join(f"{r}={v or 'no report'}" for r, v in p.reports.items()) + ".",
                       kind="percept", data={"weather": p.weather, "reports": p.reports, "tasks": self.task_list()})

    # ------------------------------------------------------------------ decision = run tasks 1-5
    def decide(self) -> Decision:
        p = self.percepts[-1]
        o = p.order
        b = self.board
        routes = by_distance(p)

        def accept():
            b["order"] = o
            return f"Order {o.order_id} accepted: {o.food} from {o.restaurant} to {o.customer}."

        def check_order():
            b["budget"] = o.deadline_min - o.prep_min
            b["urgent"] = o.urgent
            return (f"Deadline {o.deadline_min:g} min, preparation {o.prep_min:g} min -> ride budget {b['budget']:g} min; "
                    f"priority {'URGENT' if o.urgent else 'normal'}.")

        def traffic():
            known = latest_known(self.percepts)
            b["levels"] = {r: k["level"] for r, k in known.items()}
            b["heavy"] = [r for r in routes if b["levels"][r] == "heavy"]
            return ("Latest known traffic: " + ", ".join(f"{r}={k['level'] or 'unknown'}" + (f" (from {k['seen']})" if k['level'] and not k.get('latest') else "")
                                                        for r, k in known.items())
                    + f". Reject heavy: {', '.join(b['heavy']) or 'none'}.")

        def weather():
            b["flooded"] = [r for r in routes if p.weather == "rain" and p.routes[r]["flood_prone"]]
            return f"Weather {p.weather}{' at night' if p.night else ''}. Reject flooded: {', '.join(b['flooded']) or 'none'}."

        def select():
            feasible = [r for r in routes if r not in b["heavy"] and r not in b["flooded"]]
            relaxed = ""
            if not feasible:
                feasible = [r for r in routes if r not in b["flooded"]] or list(routes)
                relaxed = " No route passed both checks, so the traffic constraint was relaxed."
            rows = {r: estimate_row(predict(r, b["levels"], p), o.prep_min, o.deadline_min) for r in feasible}
            on_time = [r for r in feasible if rows[r]["arrival"] <= o.deadline_min]
            if on_time and not b["urgent"]:
                choice = min(on_time, key=lambda r: rows[r]["cost"])
                rule = f"it is the cheapest route that will still arrive on time ({rows[choice]['cost']:.2f} cost units)"
            elif on_time:
                choice = min(on_time, key=lambda r: rows[r]["arrival"])
                rule = f"the order is urgent, and it is the fastest route that will arrive on time (about {rows[choice]['arrival']} minutes)"
            else:
                choice = min(feasible, key=lambda r: rows[r]["arrival"])
                rule = (f"none of the remaining routes can arrive on time, so it takes the fastest one (about {rows[choice]['arrival']} "
                        "minutes) and tells the customer")
            b.update(choice=choice, rows=list(rows.values()), feasible=feasible, on_time=on_time,
                     notify=not on_time, rule=rule)
            return (f"Feasible after checks: {', '.join(feasible)}.{relaxed} Predicted on time: {', '.join(on_time) or 'none'}. "
                    f"Chose {choice}: {rule}.")

        fns = {"accept": accept, "check_order": check_order, "traffic": traffic, "weather": weather, "select": select}
        while True:
            ready = [k for k in self.ready() if k in DECISION_TASKS]
            if not ready:
                break
            k = ready[0]
            if k == "traffic":
                self._run(k, fns[k], focus=routes, marks={})
                self.trace.steps[-1].marks = {r: "rejected" for r in b["heavy"]}
            elif k == "weather":
                self._run(k, fns[k])
                self.trace.steps[-1].marks = {r: "rejected" for r in b["flooded"] + b["heavy"]}
            elif k == "select":
                self._run(k, fns[k])
                st = self.trace.steps[-1]
                st.data["rows"] = b["rows"]
                st.focus = [b["choice"]]
                st.marks = {r: ("chosen" if r == b["choice"] else "candidate" if r in b["feasible"] else "rejected") for r in routes}
            else:
                self._run(k, fns[k])
        choice = b["choice"]
        why = f"After checking traffic and weather, the 'choose the route' task picked route {choice} because {b['rule']}"
        rows = {r["route"]: r for r in b["rows"]}
        c = rows[choice]
        self.use("T1", "T2", "T3", "T4", "T5")
        if b["heavy"]:
            self.use("H1")
        if b["flooded"]:
            self.use("H2")
        if not [r for r in routes if r not in b["heavy"] and r not in b["flooded"]]:
            self.use("H3")
        self.use("H6" if b["notify"] else "H5" if b["urgent"] else "H4")
        for r in routes:
            if r == choice:
                self.note(r, "chosen", why[0].upper() + why[1:] + ".")
            elif r not in b["feasible"] and r in b["flooded"]:
                self.note(r, "rejected", "The weather check ruled it out: this road is flooded in the rain.")
            elif r not in b["feasible"]:
                self.note(r, "rejected", "The traffic check ruled it out because it has heavy traffic.")
            elif r not in b["on_time"]:
                self.note(r, "rejected", f"It passed the traffic and weather checks, but it would arrive after about {rows[r]['arrival']} "
                                         f"minutes, later than the {o.deadline_min:g}-minute deadline.")
            elif b["urgent"]:
                self.note(r, "rejected", f"It would arrive on time, but the order is urgent and this route is slower "
                                         f"(about {rows[r]['arrival']} minutes against {c['arrival']}).")
            else:
                self.note(r, "rejected", f"It would arrive on time, but it costs more ({rows[r]['cost']:.2f} against {c['cost']:.2f} cost units), "
                                         "and for a normal order the agent picks the cheapest route that is on time.")
        pred = next(r["arrival"] for r in b["rows"] if r["route"] == choice)
        self.trace.add("decide", f"Action: take route {choice}", why[0].upper() + why[1:] + ". Subtasks 6-8 run during the delivery.",
                       kind="decision", data={"tasks": self.task_list(), "route": choice}, focus=[choice], marks={choice: "chosen"})
        return Decision(choice, why, notify_customer=b["notify"], predicted_total_min=pred)

    # ------------------------------------------------------------------ execution-time subtasks 6-8
    def on_execution(self, stage: str, info: dict) -> None:
        self.use({"pickup": "T6", "ride": "T7", "delivered": "T8"}[stage])
        if stage == "pickup":
            self.tasks["pickup"]["status"] = "running"
            self._finish("pickup", f"Waited {info['prep']:g} min for the food; picked up at {self.board['order'].restaurant}.")
            self.tasks["deliver"]["status"] = "running"
            self.tasks["deliver"]["result"] = "riding..."
        elif stage == "delivered":
            self._finish("deliver", f"Rode route {info['route']} in {info['travel']:.1f} min.")
            self.tasks["confirm"]["status"] = "running"
            self._finish("confirm", ("Delivered ON TIME" if info["on_time"] else f"Delivered {info['late']:.1f} min LATE")
                         + f" at {info['total']:.1f} min." + (" Customer was notified in advance." if self.board.get("notify") else ""))

    def _finish(self, key: str, result: str) -> None:
        if any(self.tasks[d]["status"] != "completed" for d in self.tasks[key]["deps"]):
            raise RuntimeError(f"task {key} finished before its dependencies")
        self.tasks[key].update(status="completed", result=result)
        self.log.append(f"{self.tasks[key]['name']}: completed")

    def snapshot(self) -> dict:
        return {"tasks": self.task_list()}

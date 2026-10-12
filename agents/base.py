"""Common agent interface, the explainable decision trace, and the agents' road model.

Every agent follows the same cycle:   perceive(percept) ... -> decide() -> Decision
While it works, the agent writes its OWN reasoning into `self.trace`: every step
holds the actual values the agent computed (rules matched, beliefs, scores,
Q-values, task states). The dashboard only displays this trace; it never invents
explanations of its own.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from engine.city import ROUTE_IDS
from engine.environment import Percept, Trip
from engine.world import RouteEstimate, Weather, belief_traffic, evaluate_route

PHASES = ("observe", "reason", "decide", "act", "respond", "result")


@dataclass
class Decision:
    route: str
    reason: str
    notify_customer: bool = False
    predicted_total_min: Optional[float] = None   # the agent's own forecast, if it makes one

    def as_dict(self) -> dict:
        return {"route": self.route, "reason": self.reason, "notify_customer": self.notify_customer,
                "predicted_total_min": None if self.predicted_total_min is None else round(self.predicted_total_min, 2)}


@dataclass
class Step:
    phase: str
    title: str
    text: str
    kind: str = "note"
    data: Any = None
    focus: List[str] = field(default_factory=list)      # routes to highlight on the map
    marks: Dict[str, str] = field(default_factory=dict)  # route -> checking | candidate | rejected | chosen

    def as_dict(self) -> dict:
        return {"phase": self.phase, "title": self.title, "text": self.text, "kind": self.kind,
                "data": self.data, "focus": self.focus, "marks": self.marks}


class Trace:
    def __init__(self) -> None:
        self.steps: List[Step] = []

    def add(self, phase: str, title: str, text: str, kind: str = "note", data: Any = None,
            focus: Optional[List[str]] = None, marks: Optional[Dict[str, str]] = None) -> Step:
        assert phase in PHASES, phase
        s = Step(phase, title, text, kind, data, list(focus or []), dict(marks or {}))
        self.steps.append(s)
        return s


class Agent(ABC):
    key = "base"
    name = "Agent"
    short = "Agent"
    architecture = ""
    color = "#888888"
    info: Dict[str, Any] = {}
    diagram: Dict[str, Any] = {}
    RULEBOOK: List[dict] = []          # readable list of the rules this architecture follows

    def __init__(self) -> None:
        self.trace = Trace()
        self.route_notes: Dict[str, dict] = {}
        self.fired: List[str] = []

    def reset(self) -> None:
        """Start a new delivery episode."""
        self.trace = Trace()
        self.route_notes = {}
        self.fired = []

    def use(self, *rule_ids: str) -> None:
        """Record that these rulebook rules were applied in this decision."""
        for r in rule_ids:
            if r not in self.fired:
                self.fired.append(r)

    def note(self, route: str, status: str, reason: str) -> None:
        """Record why a route was chosen, rejected or never considered (written by the agent while deciding)."""
        self.route_notes[route] = {"status": status, "reason": reason}

    @abstractmethod
    def perceive(self, percept: Percept) -> None: ...

    @abstractmethod
    def decide(self) -> Decision: ...

    # Optional hooks, called by the simulation runner while the delivery is executed.
    def on_execution(self, stage: str, info: dict) -> None:
        """stage: pickup | ride | delivered."""

    def learn(self, trip: Trip) -> Optional[dict]:
        """Feedback after the delivery. Only the Learning agent changes itself here."""
        return None

    def snapshot(self) -> Optional[dict]:
        """Agent-specific state for the reasoning panel (e.g. the hierarchical task tree)."""
        return None

    @classmethod
    def meta(cls) -> dict:
        return {"key": cls.key, "name": cls.name, "short": cls.short, "architecture": cls.architecture,
                "color": cls.color, "info": cls.info, "diagram": cls.diagram, "rulebook": cls.RULEBOOK}


# --------------------------------------------------------------------------- the agents' road model
def predict(route_id: str, levels: Dict[str, Optional[str]], percept: Percept) -> RouteEstimate:
    """Forecast a route from BELIEVED traffic levels (unknown -> 'normal').

    This is the same deterministic formula a navigation app uses. It knows the map,
    speeds, signals, rain and flooding, but not the random variation or incidents
    the environment will add during execution.
    """
    return evaluate_route(route_id, belief_traffic(levels, delivery=percept.delivery), Weather(percept.weather, percept.night),
                          percept.delivery)


def latest_known(percepts: List[Percept]) -> Dict[str, dict]:
    """Most recent report per route across all percepts received this episode."""
    out = {r: {"level": None, "seen": None} for r in ROUTE_IDS}
    for p in sorted(percepts, key=lambda x: x.minute):
        for r, v in p.reports.items():
            if v is not None:
                out[r] = {"level": v, "seen": p.clock, "latest": p.is_latest}
    return out


def by_distance(percept: Percept) -> List[str]:
    return sorted(ROUTE_IDS, key=lambda r: (percept.routes[r]["distance_km"], r))


def fmt_levels(levels: Dict[str, Optional[str]]) -> str:
    return ", ".join(f"{r}: {v or 'no report'}" for r, v in levels.items())


def estimate_row(e: RouteEstimate, prep: float, deadline: float) -> dict:
    arrival = prep + e.travel_min
    return {"route": e.route_id, "km": round(e.distance_km, 2), "travel": round(e.travel_min, 1),
            "arrival": round(arrival, 1), "slack": round(deadline - arrival, 1), "cost": round(e.cost, 2),
            "safety": round(e.safety, 2), "risk": round(e.incident_prob, 3), "toll": e.toll,
            "flooded": e.flood_km > 0}

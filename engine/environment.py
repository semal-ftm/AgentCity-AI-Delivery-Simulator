"""Delivery environment: produces percepts and executes the agent's chosen action.

An agent never sees the true traffic directly. It receives a stream of percepts
(two traffic feeds, the second possibly incomplete), decides on a route, and the
environment then executes that route minute by minute on the road network with
the TRUE traffic, random speed variation, red lights and possible incidents.
The same performance measure (reward) scores every agent.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .city import NETWORK, ROUTE_IDS, SIGNALS, TOLL_CU, delivery_paths
from .scenarios import Order, Scenario
from .world import (ROUTE_FACTS_BY_DELIVERY, SIGNAL_WAIT, TOLL_KEY, RouteEstimate, edge_safety,
                    evaluate_route, route_cost, INCIDENT_RATE, TRAFFIC_FACTOR)

# Performance measure (identical for all agents)
R_ON_TIME = 10.0
R_LATE_PER_MIN = 0.8
R_URGENT_LATE = 5.0
R_COST = 0.3
R_UNSAFE = 15.0
R_INCIDENT = 10.0
INCIDENT_SAFETY_HIT = 0.15


@dataclass
class Percept:
    clock: str
    minute: int
    is_latest: bool
    weather: str
    night: bool
    time_of_day: str
    order: Order
    reports: Dict[str, Optional[str]]          # per-route traffic report, None = no report
    routes: Dict[str, dict]                    # static map facts per route
    delivery: int = 1                          # which source -> destination the routes belong to

    def summary(self) -> str:
        rep = ", ".join(f"{r}={v or 'no report'}" for r, v in self.reports.items())
        return f"@{self.clock}: weather={self.weather}; traffic {rep}"


@dataclass
class Segment:
    a: tuple
    b: tuple
    street: str
    zone: str
    level: str
    km: float
    start: float          # minutes after the order was placed
    drive_min: float
    wait_min: float       # red light at the end of the segment
    end: float
    incident: Optional[str] = None


@dataclass
class Trip:
    route: str
    prep_min: float
    segments: List[Segment]
    travel_min: float
    total_min: float
    deadline_min: float
    on_time: bool
    late_min: float
    distance_km: float
    cost: float
    safety: float
    incident: bool
    reward: float
    events: List[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "route": self.route, "prep_min": self.prep_min, "travel_min": round(self.travel_min, 2),
            "total_min": round(self.total_min, 2), "deadline_min": self.deadline_min, "on_time": self.on_time,
            "late_min": round(self.late_min, 2), "distance_km": round(self.distance_km, 2),
            "cost": round(self.cost, 2), "safety": round(self.safety, 3), "incident": self.incident,
            "reward": round(self.reward, 2), "events": self.events,
            "segments": [{"a": s.a, "b": s.b, "street": s.street, "zone": s.zone, "level": s.level, "km": s.km,
                          "start": round(s.start, 3), "drive": round(s.drive_min, 3), "wait": round(s.wait_min, 3),
                          "end": round(s.end, 3), "incident": s.incident} for s in self.segments],
        }


def reward(on_time: bool, late_min: float, urgent: bool, cost: float, safety: float, incident: bool) -> float:
    r = R_ON_TIME if on_time else -R_LATE_PER_MIN * late_min - (R_URGENT_LATE if urgent else 0.0)
    return r - R_COST * cost - R_UNSAFE * (1.0 - safety) - (R_INCIDENT if incident else 0.0)


class DeliveryEnvironment:
    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.traffic = scenario.traffic_model
        self.weather = scenario.weather_model

    # ---------------------------------------------------------------- perception
    def percepts(self) -> List[Percept]:
        s = self.scenario
        feeds = sorted(s.feeds, key=lambda f: f.minute)
        return [Percept(f.clock, f.minute, i == len(feeds) - 1, s.weather, s.night, s.time_of_day, s.order,
                        s.reports(f), {r: dict(v) for r, v in ROUTE_FACTS_BY_DELIVERY[s.delivery].items()}, s.delivery)
                for i, f in enumerate(feeds)]

    # ---------------------------------------------------------------- ground truth (for display / testing)
    def true_estimate(self, route_id: str) -> RouteEstimate:
        """Expected outcome with the real traffic but no noise: what a perfect navigation app would show."""
        return evaluate_route(route_id, self.traffic, self.weather, self.scenario.delivery)

    # ---------------------------------------------------------------- execution
    def execute(self, route_id: str, rng: random.Random) -> Trip:
        if route_id not in ROUTE_IDS:
            raise ValueError(f"unknown route {route_id!r}")
        order = self.scenario.order
        path = delivery_paths(self.scenario.delivery)[route_id]
        noise = self.traffic.sample_noise(rng)
        t = float(order.prep_min)
        segs: List[Segment] = []
        events = [{"t": 0.0, "kind": "order", "text": f"Order {order.order_id} placed at {order.restaurant}"},
                  {"t": t, "kind": "pickup", "text": f"Food ready after {order.prep_min} min; rider departs"}]
        incident = False
        safety_km = 0.0
        dist = 0.0
        toll = 0.0
        for i, e in enumerate(NETWORK.path_edges(path)):
            lvl = self.traffic.level(e.street.zone)
            drive = e.length_km / e.street.speed_kmh * 60 * TRAFFIC_FACTOR[lvl] * self.weather.time_factor(e) * noise[e.street.zone]
            s_e = edge_safety(e, lvl, self.weather)
            note = None
            if not incident and rng.random() < min(0.9, INCIDENT_RATE * (1.0 - s_e) * e.length_km):
                incident = True
                delay = rng.uniform(3.0, 7.0)
                kind = "skid on flooded road" if self.weather.flooded(e) else (
                    "slipped on wet road" if self.weather.condition == "rain" else "near-miss with a car")
                note = f"{kind} on {e.street.name} (+{delay:.1f} min)"
                drive += delay
                events.append({"t": round(t + drive, 2), "kind": "incident", "text": note})
            end_node = path[i + 1]
            wait = rng.uniform(0, 2 * SIGNAL_WAIT[lvl]) if (end_node in SIGNALS and end_node != path[-1]) else 0.0
            if wait > 0.05:
                events.append({"t": round(t + drive, 2), "kind": "signal", "text": f"Red light at {e.street.name} junction ({wait * 60:.0f} s)"})
            if e.key == TOLL_KEY:
                toll += TOLL_CU
                events.append({"t": round(t + drive / 2, 2), "kind": "toll", "text": f"Paid toll {TOLL_CU:.1f} CU"})
            segs.append(Segment(path[i], path[i + 1], e.street.id, e.street.zone, lvl, e.length_km, t, drive, wait, t + drive + wait, note))
            t += drive + wait
            safety_km += s_e * e.length_km
            dist += e.length_km
        total = t
        travel = total - order.prep_min
        late = max(0.0, total - order.deadline_min)
        on_time = late <= 0.0
        safety = safety_km / dist - (INCIDENT_SAFETY_HIT if incident else 0.0)
        cost = route_cost(dist, toll, travel)
        events.append({"t": round(total, 2), "kind": "delivered",
                       "text": f"Delivered at {total:.1f} min - " + ("on time" if on_time else f"{late:.1f} min late")})
        return Trip(route_id, order.prep_min, segs, travel, total, order.deadline_min, on_time, late, dist, cost,
                    safety, incident, reward(on_time, late, order.urgent, cost, safety, incident), events)


__all__ = ["DeliveryEnvironment", "Percept", "Trip", "reward"]

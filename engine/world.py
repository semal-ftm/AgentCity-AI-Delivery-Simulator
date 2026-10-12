"""Traffic simulator, weather simulator and route evaluation engine.

These are the "physics" of the simulated city. The environment uses them with the
TRUE traffic to execute a delivery (plus random noise, red lights and incidents).
Agents may use the same deterministic formulas with what they BELIEVE the traffic
is, to predict a route - exactly like a rider's navigation app would.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .city import DELIVERY_IDS, NETWORK, ROUTE_META, SIGNALS, TOLL_CU, TOLL_EDGE, Edge, delivery_meta, delivery_paths, edge_key

TRAFFIC_LEVELS = ("light", "normal", "heavy")
TRAFFIC_FACTOR = {"light": 1.0, "normal": 1.3, "heavy": 2.5}   # travel-time multiplier
SIGNAL_WAIT = {"light": 0.3, "normal": 0.45, "heavy": 1.1}      # mean red-light wait (min)
HEAVY_SAFETY = 0.04                                              # congestion -> more conflicts

RAIN_TIME = 1.2            # every road is 20% slower in rain
FLOOD_TIME = 1.6           # flood-prone roads are a further 60% slower in rain
RAIN_SAFETY = {"expressway": 0.30, "arterial": 0.08, "boulevard": 0.10, "street": 0.08, "lane": 0.12, "link": 0.08}
FLOOD_SAFETY = 0.20
NIGHT_SAFETY = 0.03

COST_PER_KM = 0.20         # fuel, CU/km
COST_PER_MIN = 0.15        # rider time, CU/min
INCIDENT_RATE = 0.04       # incident probability per km per unit of risk (1 - safety)
NOISE_SIGMA = 0.10         # day-to-day variation of a zone's speed (log-normal)
TOLL_KEY = edge_key(*TOLL_EDGE)


# --------------------------------------------------------------------------- weather simulator
@dataclass(frozen=True)
class Weather:
    condition: str = "clear"   # clear | rain
    night: bool = False

    def time_factor(self, e: Edge) -> float:
        if self.condition != "rain":
            return 1.0
        return RAIN_TIME * (FLOOD_TIME if e.street.flood_prone else 1.0)

    def safety_penalty(self, e: Edge) -> float:
        p = NIGHT_SAFETY if self.night else 0.0
        if self.condition == "rain":
            p += RAIN_SAFETY[e.street.kind] + (FLOOD_SAFETY if e.street.flood_prone else 0.0)
        return p

    def flooded(self, e: Edge) -> bool:
        return self.condition == "rain" and e.street.flood_prone


# --------------------------------------------------------------------------- traffic simulator
@dataclass
class Traffic:
    """Traffic level per zone. Zones not listed are 'normal'."""
    zones: Dict[str, str] = field(default_factory=dict)

    def level(self, zone: str) -> str:
        return self.zones.get(zone, "normal")

    def sample_noise(self, rng: random.Random) -> Dict[str, float]:
        """One delivery's actual speed variation per zone (shared by all edges of the zone)."""
        zones = {e.street.zone for e in NETWORK.edges.values()}
        return {z: math.exp(rng.gauss(0.0, NOISE_SIGMA)) for z in sorted(zones)}


# --------------------------------------------------------------------------- route evaluation engine
@dataclass
class EdgeEstimate:
    a: tuple
    b: tuple
    street: str
    zone: str
    km: float
    level: str
    minutes: float
    safety: float
    signal_wait: float      # expected wait at the light at the END of this edge (0 if none)
    flooded: bool
    toll: float


@dataclass
class RouteEstimate:
    route_id: str
    edges: List[EdgeEstimate]
    distance_km: float
    travel_min: float
    signal_min: float
    signals: int
    toll: float
    cost: float
    safety: float
    flood_km: float
    incident_prob: float

    def as_dict(self) -> dict:
        return {"route": self.route_id, "distance_km": round(self.distance_km, 2), "travel_min": round(self.travel_min, 2),
                "signal_min": round(self.signal_min, 2), "signals": self.signals, "toll": self.toll,
                "cost": round(self.cost, 2), "safety": round(self.safety, 3), "flood_km": round(self.flood_km, 2),
                "incident_prob": round(self.incident_prob, 3)}


def edge_safety(e: Edge, level: str, weather: Weather) -> float:
    s = e.street.safety - weather.safety_penalty(e) - (HEAVY_SAFETY if level == "heavy" else 0.0)
    return max(0.05, min(1.0, s))


def evaluate_route(route_id: str, traffic: Traffic, weather: Weather, delivery: int = 1) -> RouteEstimate:
    """Expected travel time, cost, safety and risk of one route, edge by edge."""
    path = delivery_paths(delivery)[route_id]
    rows: List[EdgeEstimate] = []
    for i, e in enumerate(NETWORK.path_edges(path)):
        lvl = traffic.level(e.street.zone)
        minutes = e.length_km / e.street.speed_kmh * 60 * TRAFFIC_FACTOR[lvl] * weather.time_factor(e)
        end = path[i + 1]
        wait = SIGNAL_WAIT[lvl] if (end in SIGNALS and end != path[-1]) else 0.0
        rows.append(EdgeEstimate(e.a, e.b, e.street.id, e.street.zone, e.length_km, lvl, minutes,
                                 edge_safety(e, lvl, weather), wait, weather.flooded(e),
                                 TOLL_CU if e.key == TOLL_KEY else 0.0))
    dist = sum(r.km for r in rows)
    sig = sum(r.signal_wait for r in rows)
    travel = sum(r.minutes for r in rows) + sig
    toll = sum(r.toll for r in rows)
    safety = sum(r.safety * r.km for r in rows) / dist
    survive = 1.0
    for r in rows:
        survive *= 1.0 - min(0.9, INCIDENT_RATE * (1.0 - r.safety) * r.km)
    return RouteEstimate(route_id, rows, dist, travel, sig, sum(1 for r in rows if r.signal_wait > 0), toll,
                         route_cost(dist, toll, travel), safety, sum(r.km for r in rows if r.flooded), 1.0 - survive)


def route_cost(distance_km: float, toll: float, minutes: float) -> float:
    return COST_PER_KM * distance_km + toll + COST_PER_MIN * minutes


def static_route_facts(delivery: int = 1) -> Dict[str, dict]:
    """What any rider knows from the map alone (no traffic): the agents' map knowledge."""
    out = {}
    meta = delivery_meta(delivery)
    for rid, path in delivery_paths(delivery).items():
        edges = NETWORK.path_edges(path)
        km = sum(e.length_km for e in edges)
        out[rid] = {
            "route": rid, "name": meta[rid]["name"], "key_zone": meta[rid]["key_zone"],
            "distance_km": round(km, 2),
            "free_flow_min": round(sum(e.length_km / e.street.speed_kmh * 60 for e in edges), 2),
            "signals": sum(1 for n in path[1:-1] if n in SIGNALS),
            "toll": TOLL_CU if any(e.key == TOLL_KEY for e in edges) else 0.0,
            "flood_prone": any(e.street.flood_prone for e in edges),
            "base_safety": round(sum(e.street.safety * e.length_km for e in edges) / km, 3),
            "road_kinds": sorted({e.street.kind for e in edges}),
            "zones": sorted({e.street.zone for e in edges}),
        }
    return out


ROUTE_FACTS = static_route_facts()
ROUTE_FACTS_BY_DELIVERY = {d: static_route_facts(d) for d in DELIVERY_IDS}


def belief_traffic(levels_by_route: Dict[str, Optional[str]], default: str = "normal", delivery: int = 1) -> Traffic:
    """Turn per-route traffic reports into zone levels (each route reports its key zone).

    Shared zones that no feed reports (link roads, midtown) are assumed 'normal'.
    A missing report (None) is filled with `default`.
    """
    zones = {}
    for rid, lvl in levels_by_route.items():
        zones[delivery_meta(delivery)[rid]["key_zone"]] = lvl if lvl else default
    return Traffic(zones)

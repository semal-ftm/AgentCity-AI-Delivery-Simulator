"""Scenario manager: the three mandatory test situations, plus random training situations."""
from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Dict, List, Optional

from .city import DELIVERIES, ROUTE_IDS, delivery_meta
from .world import TRAFFIC_LEVELS, Traffic, Weather

DATA = Path(__file__).resolve().parent.parent / "data" / "scenarios.json"


@dataclass
class Order:
    order_id: str
    restaurant: str
    customer: str
    food: str
    prep_min: float
    deadline_min: float      # minutes from order time until the customer expects the food
    urgent: bool


@dataclass
class Feed:
    clock: str
    minute: int                                   # relative to the decision time (0 = now)
    offline: List[str] = field(default_factory=list)
    override: Dict[str, str] = field(default_factory=dict)   # what that (older) feed reported instead


@dataclass
class Scenario:
    id: int
    name: str
    short: str
    description: str
    clock: str
    time_of_day: str
    night: bool
    weather: str
    traffic: Dict[str, str]
    feeds: List[Feed]
    order: Order
    delivery: int = 1          # which source -> destination (1 = default, 2 = top-to-bottom)

    @property
    def weather_model(self) -> Weather:
        return Weather(self.weather, self.night)

    @property
    def traffic_model(self) -> Traffic:
        return Traffic(dict(self.traffic))

    def reports(self, feed: Feed) -> Dict[str, Optional[str]]:
        """Per-route traffic reports in one feed (None = sensor offline / no report)."""
        t = self.traffic_model
        meta = delivery_meta(self.delivery)
        return {rid: None if rid in feed.offline else feed.override.get(rid, t.level(meta[rid]["key_zone"]))
                for rid in ROUTE_IDS}

    def to_dict(self) -> dict:
        d = asdict(self)
        d["feeds"] = [{**asdict(f), "reports": self.reports(f)} for f in self.feeds]
        return d


def _from_dict(d: dict) -> Scenario:
    return Scenario(
        id=d["id"], name=d["name"], short=d.get("short", d["name"]), description=d.get("description", ""),
        clock=d["clock"], time_of_day=d.get("time_of_day", ""), night=bool(d.get("night", False)),
        weather=d["weather"], traffic=dict(d["traffic"]),
        feeds=[Feed(f["clock"], int(f["minute"]), list(f.get("offline", [])), dict(f.get("override", {})))
               for f in d["feeds"]],
        order=Order(**d["order"]),
    )


def load_scenarios(path: Path = DATA) -> List[Scenario]:
    with open(path, encoding="utf-8") as fh:
        return [_from_dict(d) for d in json.load(fh)["situations"]]


SCENARIOS = load_scenarios()


def with_delivery(sc: Scenario, delivery: int) -> Scenario:
    """The same situation (time, weather, traffic, deadline) on another source -> destination."""
    if delivery == sc.delivery:
        return sc
    D = DELIVERIES[delivery]
    order = replace(sc.order, order_id=sc.order.order_id.replace("-1", f"-{delivery}", 1),
                    restaurant=D["restaurant_name"] or sc.order.restaurant, customer=D["customer_name"] or sc.order.customer,
                    deadline_min=sc.order.deadline_min + D["extra_min"])
    return replace(sc, order=order, delivery=delivery)


def get_scenario(sid: int, delivery: int = 1) -> Scenario:
    if delivery not in DELIVERIES:
        raise KeyError(f"unknown delivery {delivery}")
    for s in SCENARIOS:
        if s.id == sid:
            return with_delivery(s, delivery)
    raise KeyError(f"unknown situation {sid}")


def random_scenario(rng: random.Random, base: Optional[Scenario] = None, delivery: int = 1) -> Scenario:
    """A random delivery situation for training the Learning agent.

    With `base`, the situation is a mandatory one (the agent gains experience in
    the same conditions it will be tested in); otherwise every factor is random.
    """
    if base is not None:
        return with_delivery(base, delivery)
    zones = {z: rng.choice(TRAFFIC_LEVELS) for z in ("downtown", "ring", "oldtown", "expressway", "midtown")}
    zones["links"] = "normal"
    weather = "rain" if rng.random() < 0.4 else "clear"
    night = rng.random() < 0.3
    offline = [r for r in ROUTE_IDS if rng.random() < 0.15]
    urgent = rng.random() < 0.35
    return Scenario(
        id=0, name="Training situation", short="random", description="", clock="--:--",
        time_of_day="night" if night else "day", night=night, weather=weather, traffic=zones,
        feeds=[Feed("-10", -10, []), Feed("now", 0, offline)],
        order=Order("TRAIN", "Training kitchen", "Training customer", "meal", rng.choice([4, 5, 6, 8]),
                    rng.choice([20, 23, 25, 28, 30, 35, 40]) + DELIVERIES[delivery]["extra_min"], urgent),
        delivery=delivery,
    )

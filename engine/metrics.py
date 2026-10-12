"""Performance metrics: evaluate one decision over many simulated executions.

Every agent is evaluated with the SAME random seeds (common random numbers), so two
agents that choose the same route get identical results, and differences between
agents come only from their decisions.
"""
from __future__ import annotations

import random
from statistics import mean, pstdev
from typing import List

from .environment import DeliveryEnvironment, Trip
from .scenarios import Scenario


def run_rng(seed: int, scenario_id: int, run_index: int) -> random.Random:
    return random.Random(seed * 1_000_003 + scenario_id * 10_007 + run_index)


def stream_id(scenario: Scenario) -> int:
    """Random-stream id of a situation; delivery 1 keeps its original ids so its results never change."""
    return scenario.id + 100 * (scenario.delivery - 1)


def execute_runs(scenario: Scenario, route: str, runs: int, seed: int) -> List[Trip]:
    env = DeliveryEnvironment(scenario)
    return [env.execute(route, run_rng(seed, stream_id(scenario), i)) for i in range(runs)]


def summarize(trips: List[Trip]) -> dict:
    n = len(trips)
    tot = [t.total_min for t in trips]
    return {
        "runs": n,
        "time": round(mean(tot), 2), "time_sd": round(pstdev(tot), 2),
        "time_p90": round(sorted(tot)[int(0.9 * (n - 1))], 2),
        "travel": round(mean(t.travel_min for t in trips), 2),
        "cost": round(mean(t.cost for t in trips), 2),
        "safety": round(mean(t.safety for t in trips), 3),
        "on_time": round(100 * sum(t.on_time for t in trips) / n, 1),
        "late": round(mean(t.late_min for t in trips), 2),
        "incidents": round(100 * sum(t.incident for t in trips) / n, 1),
        "reward": round(mean(t.reward for t in trips), 2),
        "distance": round(trips[0].distance_km, 2),
    }

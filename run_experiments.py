"""Run all 7 agents on all 3 situations and write the report outputs.

    python run_experiments.py                 # seed 42, 200 runs per decision, 1500 training episodes
    python run_experiments.py --runs 500 --episodes 3000 --seed 7

Writes results/results.csv, results/results.json, results/results_summary.md,
results/figures/*.png (comparison charts) and results/diagrams/*.svg (architecture diagrams).
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from agents import REGISTRY, Brain
from engine.scenarios import SCENARIOS
from sim.diagrams import diagram_svg, system_svg
from sim.runner import compare

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results"
COLS = ["situation", "agent", "route", "notify", "predicted", "time", "time_sd", "cost", "safety", "on_time", "late", "incidents", "reward", "utility", "reason"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--runs", type=int, default=200)
    ap.add_argument("--episodes", type=int, default=1500)
    a = ap.parse_args()

    brain = Brain()
    learning = brain.train(a.episodes, a.seed)
    brain.save(ROOT / "data" / "q_table.json")
    rows = []
    for sc in SCENARIOS:
        for r in compare(sc, brain, a.seed, a.runs):
            rows.append({"situation": sc.id, "situation_name": sc.name, **r})

    OUT.mkdir(exist_ok=True)
    with open(OUT / "results.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows({**r, "agent": r["name"]} for r in rows)
    with open(OUT / "results.json", "w", encoding="utf-8") as fh:
        json.dump({"settings": {"seed": a.seed, "runs": a.runs, "episodes": a.episodes},
                   "learning": {k: learning[k] for k in ("first_avg", "last_avg", "window", "states")},
                   "results": rows}, fh, indent=1)
    write_markdown(rows, learning, a)
    write_figures(rows, learning)
    d = OUT / "diagrams"
    d.mkdir(exist_ok=True)
    (d / "0_system.svg").write_text(system_svg(), encoding="utf-8")
    for i, cls in enumerate(REGISTRY.values(), 1):
        (d / f"{i}_{cls.key}.svg").write_text(diagram_svg(cls.meta()), encoding="utf-8")
    print_console(rows, learning)
    write_delivery2(a)


def write_delivery2(a) -> None:
    """The optional second source -> destination: separate files, so the main results above never change."""
    from engine.city import DELIVERIES
    from engine.scenarios import get_scenario
    brain = Brain()
    learning = brain.train(a.episodes, a.seed, delivery=2)
    brain.save(ROOT / "data" / "q_table_delivery2.json")
    rows = []
    for base in SCENARIOS:
        sc = get_scenario(base.id, 2)
        for r in compare(sc, brain, a.seed, a.runs):
            rows.append({"situation": sc.id, "situation_name": sc.name, "deadline": sc.order.deadline_min, **r})
    out = OUT / "delivery2"
    out.mkdir(exist_ok=True)
    with open(out / "results.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows({**r, "agent": r["name"]} for r in rows)
    D = DELIVERIES[2]
    lines = [f"# Delivery 2 results: {D['from']} -> {D['to']} ({D['direction']})", "",
             f"Same three situations as delivery 1; this trip is longer, so each deadline is {D['extra_min']} minutes later. "
             f"Seed {a.seed}, {a.runs} runs per decision; the Learning agent has its own memory for this delivery "
             f"(mean training reward {learning['first_avg']} -> {learning['last_avg']}).", ""]
    for base in SCENARIOS:
        lines += [f"## Situation {base.id}: {base.name} (deadline {base.order.deadline_min + D['extra_min']:g} min)", "",
                  "| Agent | Route | Mean time | Cost | Safety | On time | Reward |", "|---|---|---|---|---|---|---|"]
        for r in [x for x in rows if x["situation"] == base.id]:
            lines.append(f"| {r['name']} | {r['route']} | {r['time']} | {r['cost']} | {r['safety']} | {r['on_time']}% | {r['reward']:+.2f} |")
        lines.append("")
    lines += ["## Mean reward over the three situations", "", "| Agent | Mean reward |", "|---|---|"]
    for key, cls in REGISTRY.items():
        rs = [x["reward"] for x in rows if x["agent"] == key]
        lines.append(f"| {cls.name} | {sum(rs) / len(rs):+.2f} |")
    (out / "results_summary.md").write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    print(f"Delivery 2 results written to {out}")


def write_markdown(rows, learning, a) -> None:
    lines = [f"# Results (seed {a.seed}, {a.runs} simulated runs per decision, learning agent trained for {a.episodes} episodes)", "",
             "All data is simulated. Times in minutes from order placement; cost in simulated cost units (CU).", ""]
    for sc in SCENARIOS:
        lines += [f"## Situation {sc.id}: {sc.name}", "", f"Deadline {sc.order.deadline_min:g} min{' (urgent)' if sc.order.urgent else ''}.", "",
                  "| Agent | Route | Forecast | Mean time | Cost | Safety | On time | Incidents | Reward |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for r in [x for x in rows if x["situation"] == sc.id]:
            lines.append(f"| {r['name']} | {r['route']}{' (notify)' if r['notify'] else ''} | {r['predicted'] if r['predicted'] is not None else '-'} | "
                         f"{r['time']} | {r['cost']} | {r['safety']} | {r['on_time']}% | {r['incidents']}% | {r['reward']:+.2f} |")
        lines.append("")
    lines += ["## Mean reward over the three situations", "", "| Agent | S1 | S2 | S3 | Mean |", "|---|---|---|---|---|"]
    for key, cls in REGISTRY.items():
        rs = [next(x for x in rows if x["situation"] == s.id and x["agent"] == key)["reward"] for s in SCENARIOS]
        lines.append(f"| {cls.name} | " + " | ".join(f"{v:+.2f}" for v in rs) + f" | **{sum(rs) / 3:+.2f}** |")
    lines += ["", f"Learning agent: mean reward {learning['first_avg']} over the first {learning['window']} training episodes, "
              f"{learning['last_avg']} over the last {learning['window']}."]
    (OUT / "results_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_figures(rows, learning) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig_dir = OUT / "figures"
    fig_dir.mkdir(exist_ok=True)
    agents = list(REGISTRY.values())
    colors = ["#2a6fdb", "#e0a000", "#d1495b"]
    charts = [("time", "Mean delivery time (min)", "1_delivery_time.png"), ("cost", "Mean cost (CU)", "2_cost.png"),
              ("safety", "Mean safety (0-1)", "3_safety.png"), ("on_time", "Deliveries on time (%)", "4_deadline_success.png"),
              ("reward", "Mean reward (performance measure)", "5_reward.png")]
    for key, label, fname in charts:
        fig, ax = plt.subplots(figsize=(10, 4.4))
        w = 0.26
        for i, sc in enumerate(SCENARIOS):
            vals = [next(x for x in rows if x["situation"] == sc.id and x["agent"] == c.key)[key] for c in agents]
            xs = [j + (i - 1) * w for j in range(len(agents))]
            ax.bar(xs, vals, w * 0.92, color=colors[i], label=f"S{sc.id}: {sc.short}")
            if key == "time":
                ax.hlines(sc.order.deadline_min, xs[0] - w / 2, xs[-1] + w / 2, colors=colors[i], linestyles="dashed", linewidth=1)
        ax.set_xticks(range(len(agents)), [c.short for c in agents])
        ax.set_ylabel(label)
        if key == "time":
            ax.set_title("dashed line = that situation's deadline", fontsize=9, loc="right", color="#555")
        ax.axhline(0, color="#333", linewidth=0.8)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", alpha=0.25)
        ax.legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.13))
        fig.tight_layout()
        fig.savefig(fig_dir / fname, dpi=150)
        plt.close(fig)
    curve = learning["curve"]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.scatter([p["episode"] for p in curve], [p["reward"] for p in curve], s=3, color="#2a6fdb", alpha=0.25, label="episode reward")
    ax.plot([p["episode"] for p in curve], [p["avg"] for p in curve], color="#d1495b", linewidth=2, label="moving average (50)")
    ax.set_xlabel("training episode")
    ax.set_ylabel("reward")
    ax.set_ylim(-35, 12)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(fig_dir / "6_learning_curve.png", dpi=150)
    plt.close(fig)


def print_console(rows, learning) -> None:
    for sc in SCENARIOS:
        print(f"\nSituation {sc.id}: {sc.name}  (deadline {sc.order.deadline_min:g} min)")
        print(f"  {'Agent':26} {'Route':6} {'Time':>6} {'Cost':>6} {'Safety':>7} {'OnTime':>7} {'Reward':>7}")
        for r in [x for x in rows if x["situation"] == sc.id]:
            print(f"  {r['name']:26} {r['route']:6} {r['time']:6.2f} {r['cost']:6.2f} {r['safety']:7.3f} {r['on_time']:6.1f}% {r['reward']:+7.2f}")
    print(f"\nLearning agent: reward {learning['first_avg']} (first {learning['window']}) -> {learning['last_avg']} (last {learning['window']})")
    print(f"Outputs written to {OUT}")


if __name__ == "__main__":
    main()

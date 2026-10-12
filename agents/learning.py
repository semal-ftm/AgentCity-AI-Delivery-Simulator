"""Agent 5 - Learning Agent (tabular Q-learning).

State  s = (weather, urgency, last known traffic report of routes A, B, C, D)
Action a = route A | B | C | D
Reward r = the environment's performance measure for the finished delivery

Each delivery is one episode with a single decision, so the next state is terminal
and the Q-learning update reduces to

    Q(s,a) <- Q(s,a) + alpha * (r + gamma * max_a' Q(s',a') - Q(s,a)),   with max Q(s') = 0 (terminal)
           =  Q(s,a) + alpha * (r - Q(s,a))

The learning rate is alpha = max(0.02, 1/n), where n is the number of times (s,a) has
been tried: a sample average of the rewards, so one unlucky incident does not swing
the estimate (rewards are noisy because travel times and incidents are random).

TRAINING uses epsilon-greedy exploration on many simulated deliveries (half are the
three test situations, half random situations). TESTING uses the learned greedy
policy (epsilon = 0) on separate random seeds. Nothing is hard-coded: the policy
comes only from the rewards the agent received.
"""
from __future__ import annotations

import copy
import json
import random
from pathlib import Path
from typing import Dict, List, Optional

from engine.city import ROUTE_IDS
from engine.environment import DeliveryEnvironment, Percept, Trip
from engine.scenarios import SCENARIOS, random_scenario

from .base import Agent, Decision, latest_known

ABBR = {"light": "L", "normal": "N", "heavy": "H", None: "?"}


def state_of(percepts: List[Percept]) -> str:
    p = percepts[-1]
    known = latest_known(percepts)
    tr = " ".join(f"{r}{ABBR[known[r]['level']]}" for r in ROUTE_IDS)
    return f"{p.weather}|{'urgent' if p.order.urgent else 'normal'}|{tr}"


def explain_state(s: str) -> str:
    w, u, tr = s.split("|")
    names = {"L": "light", "N": "normal", "H": "heavy", "?": "unknown"}
    return f"weather={w}, order={u}, traffic " + ", ".join(f"{t[0]}={names[t[1]]}" for t in tr.split())


class Brain:
    """The learned knowledge (Q-table) plus the record of how it was learned."""

    def __init__(self, alpha_min: float = 0.02, gamma: float = 0.0) -> None:
        self.alpha_min, self.gamma = alpha_min, gamma
        self.q: Dict[str, Dict[str, float]] = {}
        self.n: Dict[str, Dict[str, int]] = {}
        self.history: List[dict] = []
        self.settings: dict = {}

    def values(self, s: str) -> Dict[str, float]:
        return self.q.setdefault(s, {a: 0.0 for a in ROUTE_IDS})

    def visits(self, s: str) -> Dict[str, int]:
        return self.n.setdefault(s, {a: 0 for a in ROUTE_IDS})

    def greedy(self, s: str) -> Optional[str]:
        if s not in self.q or not any(self.visits(s).values()):
            return None
        v, n = self.values(s), self.visits(s)
        tried = [a for a in ROUTE_IDS if n[a] > 0]
        return max(tried, key=lambda a: (v[a], -ROUTE_IDS.index(a)))

    def update(self, s: str, a: str, r: float) -> dict:
        v = self.values(s)
        old = v[a]
        alpha = max(self.alpha_min, 1.0 / (self.visits(s)[a] + 1))   # sample average, never below alpha_min
        target = r + self.gamma * 0.0          # terminal next state: max Q(s') = 0
        v[a] = old + alpha * (target - old)
        self.visits(s)[a] += 1
        return {"state": s, "action": a, "q_old": round(old, 3), "reward": round(r, 3), "alpha": round(alpha, 4),
                "q_new": round(v[a], 3), "visits": self.n[s][a]}

    # ------------------------------------------------------------------ training
    def train(self, episodes: int = 1500, seed: int = 42, eps_start: float = 1.0, eps_end: float = 0.05,
              explore_frac: float = 0.6, mandatory_share: float = 0.5, delivery: int = 1) -> dict:
        rng = random.Random(seed)
        self.q, self.n, self.history = {}, {}, []
        self.settings = {"delivery": delivery, "episodes": episodes, "seed": seed, "alpha": f"max({self.alpha_min}, 1/n)", "gamma": self.gamma,
                         "eps_start": eps_start, "eps_end": eps_end, "mandatory_share": mandatory_share}
        decay = max(1, int(episodes * explore_frac))
        for ep in range(1, episodes + 1):
            base = rng.choice(SCENARIOS) if rng.random() < mandatory_share else None
            sc = random_scenario(rng, base, delivery)
            env = DeliveryEnvironment(sc)
            s = state_of(env.percepts())
            eps = max(eps_end, eps_start - (eps_start - eps_end) * (ep - 1) / decay)
            explore = rng.random() < eps or self.greedy(s) is None
            a = rng.choice(ROUTE_IDS) if explore else self.greedy(s)
            trip = env.execute(a, rng)
            u = self.update(s, a, trip.reward)
            self.history.append({"episode": ep, "situation": sc.id, "epsilon": round(eps, 3), "explored": explore,
                                 "on_time": trip.on_time, "minutes": round(trip.total_min, 1), **u})
        return self.summary()

    def summary(self) -> dict:
        h = self.history
        rewards = [x["reward"] for x in h]
        win = 50
        avg = [round(sum(rewards[max(0, i - win + 1):i + 1]) / (i - max(0, i - win + 1) + 1), 3) for i in range(len(rewards))]
        cut = min(150, len(h) // 4) or 1
        return {
            "settings": self.settings, "episodes": len(h), "states": len(self.q),
            "first_avg": round(sum(rewards[:cut]) / cut, 2) if h else None,
            "last_avg": round(sum(rewards[-cut:]) / cut, 2) if h else None, "window": cut,
            "curve": [{"episode": x["episode"], "reward": x["reward"], "avg": a, "epsilon": x["epsilon"]} for x, a in zip(h, avg)],
            "first_episodes": h[:8], "last_episodes": h[-8:],
        }

    def table(self, states: Optional[List[str]] = None) -> List[dict]:
        keys = states if states is not None else sorted(self.q)
        return [{"state": s, "meaning": explain_state(s), "q": {a: round(v, 2) for a, v in self.values(s).items()},
                 "n": dict(self.visits(s)), "greedy": self.greedy(s)} for s in keys]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"settings": self.settings, "q": self.q, "n": self.n}, fh, indent=1)


class LearningAgent(Agent):
    key = "learning"
    name = "Learning Agent"
    short = "Learning"
    architecture = "Tabular Q-learning from delivery rewards"
    color = "#118ab2"
    RULEBOOK = [
        {"title": "What the agent pays attention to", "rules": [
            {"id": "L1", "text": "It describes each situation by the weather, whether the order is urgent, and the last known traffic on each of the four routes."},
            {"id": "L2", "text": "Its possible actions are to take route A, B, C or D."},
            {"id": "L3", "text": "After every delivery it gets a score (reward): a bonus for arriving on time, a penalty for each minute late (bigger if urgent), and penalties for high cost, low safety and accidents."},
        ]},
        {"title": "How it decides", "rules": [
            {"id": "L4", "text": "If it has met this kind of situation before, it takes the route that earned the best average score in the past."},
            {"id": "L5", "text": "If it has never met this kind of situation, it knows nothing yet and simply takes the shortest route."},
        ]},
        {"title": "How it learns from feedback", "rules": [
            {"id": "L6", "text": "After each delivery, it updates its memory of how good that route is in that situation, moving the value towards the score it just received (an average of all the scores so far)."},
            {"id": "L7", "text": "While training, it sometimes tries a random route to discover new options. It explores a lot at first and less and less over time."},
        ]},
    ]
    info = {
        "definition": "A learning agent improves its behaviour from experience: a critic scores each result, and the learning element changes the agent's knowledge so better actions are chosen next time.",
        "principle": "observe state -> choose route (explore or exploit Q-values) -> delivery reward -> Q(s,a) <- Q(s,a) + α(r − Q(s,a)).",
        "logic": "State = weather, urgency and the last known traffic report of each route. Actions = routes A-D. Training: ε-greedy (ε decays from 1.0 to 0.05) over many simulated deliveries; each finished delivery's reward updates one Q-value with learning rate α = max(0.02, 1/n) (a running average of the rewards seen for that state and route). Testing: always take the route with the highest Q-value (no exploration). The agent is never told travel times or rules; it only sees rewards.",
        "example": "Early episodes try the downtown route in a storm and get large negative rewards; after a few hundred episodes Q(storm, D) is clearly highest, so the trained policy picks the expressway.",
        "advantages": ["Discovers effects no rule or model describes (e.g. incident risk)", "Improves with more experience", "Optimises the real performance measure directly"],
        "limitations": ["Needs many (simulated) trials before it is good", "Exploration makes bad decisions while learning", "Knows nothing about states it has never seen"],
    }
    diagram = {
        "perception": ["State: weather, urgency", "known traffic per route"],
        "extra": [{"label": "Q-table (knowledge)", "kind": "state", "lines": ["Q(s, route)"]},
                  {"label": "Critic: reward", "kind": "learning", "lines": ["on time, cost, safety, incidents"]},
                  {"label": "Learning element", "kind": "learning", "lines": ["Q <- Q + α(r − Q)"]}],
        "decision": ["Choose argmax Q (test)", "or explore (training)"],
        "action": ["Ride chosen route"],
        "environment": ["City roads, traffic, weather"],
        "feedback": "reward updates the Q-table",
    }

    def __init__(self, brain: Optional[Brain] = None) -> None:
        super().__init__()
        self.brain = copy.deepcopy(brain) if brain is not None else Brain()   # isolated copy per run
        self.percepts: List[Percept] = []
        self.state: Optional[str] = None
        self.action: Optional[str] = None

    def reset(self) -> None:
        super().reset()
        self.percepts, self.state, self.action = [], None, None

    def perceive(self, p: Percept) -> None:
        self.percepts.append(p)
        self.trace.add("observe", f"Percept @{p.clock}",
                       f"Weather {p.weather}; traffic " + ", ".join(f"{r}={v or 'no report'}" for r, v in p.reports.items()) + ".",
                       kind="percept", data={"weather": p.weather, "reports": p.reports})

    def decide(self) -> Decision:
        s = state_of(self.percepts)
        self.state = s
        b = self.brain
        q, n = dict(b.values(s)), dict(b.visits(s))
        trained = len(b.history)
        self.trace.add("reason", "Encode the current state", f"s = {s}  ({explain_state(s)}).", kind="q",
                       data={"state": s, "meaning": explain_state(s), "q": q, "n": n, "episodes": trained})
        g = b.greedy(s)
        if g is None:
            from .base import by_distance
            choice = by_distance(self.percepts[-1])[0]
            why = (f"The agent has never met this kind of situation (after {trained} practice deliveries), so it has nothing "
                   f"to go on and takes the shortest route, {choice}")
            self.trace.add("reason", "No experience for this state",
                           "All Q-values are 0 with 0 visits, so there is nothing to exploit. "
                           + ("Train the agent first." if trained == 0 else "This state never occurred in training."),
                           kind="q", data={"state": s, "q": q, "n": n})
        else:
            choice = g
            ranked = sorted(ROUTE_IDS, key=lambda a: -q[a])
            why = (f"In past deliveries in this kind of situation, route {choice} earned the best average score "
                   f"({q[choice]:.2f}, learned from {n[choice]} deliveries on that route)")
            self.trace.add("reason", "Look up learned Q-values",
                           "Q(s,·): " + ", ".join(f"{a}={q[a]:.2f} (n={n[a]})" for a in ranked) +
                           ". Greedy policy (testing, ε = 0): take the maximum.",
                           kind="q", data={"state": s, "q": q, "n": n, "chosen": choice},
                           focus=[choice], marks={a: ("chosen" if a == choice else "candidate" if n[a] else "unknown") for a in ROUTE_IDS})
        self.action = choice
        self.use("L1", "L2", "L4" if g is not None else "L5")
        for a in ROUTE_IDS:
            if a == choice:
                self.note(a, "chosen", why[0].upper() + why[1:] + ".")
            elif g is None:
                self.note(a, "not considered", "The agent has no experience of this situation yet, so it had nothing to compare.")
            elif n[a] == 0:
                self.note(a, "rejected", "The agent never tried this route in this kind of situation while practising, so it knows nothing about it.")
            else:
                self.note(a, "rejected", f"The agent tried this route {n[a]} times in this kind of situation. On average it scored "
                                         f"{q[a]:.2f}, worse than route {choice} ({q[choice]:.2f}), so experience says it is the poorer choice.")
        self.trace.add("decide", f"Action: take route {choice}", why[0].upper() + why[1:] + ".",
                       kind="decision", data={"route": choice}, focus=[choice], marks={choice: "chosen"})
        return Decision(choice, why)

    def learn(self, trip: Trip) -> dict:
        """Online update from this delivery's reward (in this run's isolated copy of the brain)."""
        u = self.brain.update(self.state, self.action, trip.reward)
        self.use("L3", "L6")
        u["formula"] = (f"Q(s,{u['action']}) <- {u['q_old']:.3f} + {u['alpha']} × ({u['reward']:.3f} − {u['q_old']:.3f}) = {u['q_new']:.3f}")
        return u

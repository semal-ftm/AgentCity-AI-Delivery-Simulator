"""HTTP server for the Agent City dashboard (Python standard library only).

    GET  /api/init            world map, situations, agents, learning summary
    POST /api/run             {situation, agent, run_index}  -> replayable timeline
    POST /api/compare         {situation}                     -> all 7 agents, same conditions
    GET  /api/compare_all                                     -> 7 agents x 3 situations
    GET  /api/diagram/<agent>.svg                             -> architecture diagram (or "system")
    POST /api/train           {episodes, seed}                -> retrain the learning agent
    POST /api/test_policy     {runs}                          -> evaluate the learned greedy policy
"""
from __future__ import annotations

import json
import mimetypes
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from agents import REGISTRY, Brain, make_agent
from engine.city import DELIVERY_IDS, world_json
from engine.environment import DeliveryEnvironment
from engine.metrics import execute_runs, summarize
from engine.scenarios import SCENARIOS, get_scenario
from sim.diagrams import diagram_svg, system_svg
from sim.runner import build_run, compare
from agents.learning import state_of

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
Q_FILES = {1: ROOT / "data" / "q_table.json", 2: ROOT / "data" / "q_table_delivery2.json"}

DEFAULTS = {"seed": 42, "runs": 200, "episodes": 1500}
API_VERSION = 4          # bump when the run format changes; the page checks it


class App:
    """Delivery 1 is the default source -> destination; delivery 2 is the optional top-to-bottom one.
    The Learning agent keeps a separate memory (Q-table) for each delivery."""

    def __init__(self, episodes: int = DEFAULTS["episodes"], seed: int = DEFAULTS["seed"], save: bool = True) -> None:
        self.lock = threading.Lock()
        self.save = save
        self.seed = seed
        self.runs = DEFAULTS["runs"]
        self.brains = {d: Brain() for d in DELIVERY_IDS}
        self.version = 0
        self.cache: dict = {}
        self.train(episodes, seed)

    @property
    def brain(self) -> Brain:
        return self.brains[1]

    @staticmethod
    def _delivery(d) -> int:
        d = int(d or 1)
        if d not in DELIVERY_IDS:
            raise ValueError(f"unknown delivery {d}")
        return d

    # ------------------------------------------------------------------ learning
    def train(self, episodes: int, seed: int) -> dict:
        episodes = max(50, min(20000, int(episodes)))
        with self.lock:
            for d in DELIVERY_IDS:
                brain = Brain()
                brain.train(episodes, int(seed), delivery=d)
                self.brains[d] = brain
                if self.save:
                    try:
                        brain.save(Q_FILES[d])
                    except OSError:
                        pass
            self.version += 1
            self.cache.clear()
        return self.learning_summary(1)

    def learning_summary(self, delivery: int = 1) -> dict:
        b = self.brains[delivery]
        s = b.summary()
        test_states = {sc.id: state_of(DeliveryEnvironment(get_scenario(sc.id, delivery)).percepts()) for sc in SCENARIOS}
        s["test_states"] = {sid: b.table([st])[0] for sid, st in test_states.items()}
        s["version"] = self.version
        s["delivery"] = delivery
        s["q_file"] = f"data/{Q_FILES[delivery].name}"
        return s

    def test_policy(self, runs: int, delivery: int = 1) -> dict:
        runs = max(10, min(2000, int(runs)))
        out = []
        for base in SCENARIOS:
            sc = get_scenario(base.id, delivery)
            agent = make_agent("learning", self.brains[delivery])
            agent.reset()
            for p in DeliveryEnvironment(sc).percepts():
                agent.perceive(p)
            d = agent.decide()
            # separate seeds from the dashboard runs: testing never reuses training randomness
            m = summarize(execute_runs(sc, d.route, runs, self.seed + 10_000))
            best = max(("A", "B", "C", "D"), key=lambda r: summarize(execute_runs(sc, r, runs, self.seed + 10_000))["reward"])
            out.append({"situation": sc.id, "name": sc.name, "route": d.route, "best_route": best, "reason": d.reason, **m})
        return {"runs": runs, "rows": out, "version": self.version}

    # ------------------------------------------------------------------ simulation
    def run(self, sid: int, agent: str, run_index: int, delivery: int = 1) -> dict:
        if agent not in REGISTRY:
            raise ValueError(f"unknown agent {agent}")
        delivery = self._delivery(delivery)
        run_index = max(0, min(self.runs - 1, int(run_index)))
        key = ("run", delivery, sid, agent, run_index, self.version)
        if key not in self.cache:
            self.cache[key] = build_run(get_scenario(sid, delivery), agent, self.brains[delivery], self.seed, run_index, self.runs)
        return self.cache[key]

    def compare(self, sid: int, delivery: int = 1) -> dict:
        delivery = self._delivery(delivery)
        key = ("cmp", delivery, sid, self.version)
        if key not in self.cache:
            sc = get_scenario(sid, delivery)
            self.cache[key] = {"situation": sid, "delivery": delivery, "name": sc.name, "runs": self.runs, "seed": self.seed,
                               "rows": compare(sc, self.brains[delivery], self.seed, self.runs)}
        return self.cache[key]

    def init(self) -> dict:
        return {"api_version": API_VERSION, "world": world_json(), "situations": [s.to_dict() for s in SCENARIOS],
                "situations_by_delivery": {d: [get_scenario(s.id, d).to_dict() for s in SCENARIOS] for d in DELIVERY_IDS},
                "agents": [c.meta() for c in REGISTRY.values()],
                "settings": {"seed": self.seed, "runs": self.runs}, "learning": self.learning_summary(1),
                "learning_by_delivery": {d: self.learning_summary(d) for d in DELIVERY_IDS}}


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # keep the console quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}") if n else {}

        def do_GET(self):
            path = urlparse(self.path).path
            try:
                if path == "/api/init":
                    return self._json(app.init())
                if path == "/api/compare_all":
                    d = parse_qs(urlparse(self.path).query).get("delivery", ["1"])[0]
                    return self._json([app.compare(s.id, int(d)) for s in SCENARIOS])
                if path.startswith("/api/diagram/") and path.endswith(".svg"):
                    key = path[len("/api/diagram/"):-4]
                    svg = system_svg() if key == "system" else diagram_svg(REGISTRY[key].meta())
                    return self._send(200, svg.encode("utf-8"), "image/svg+xml; charset=utf-8")
                if path.startswith("/api/"):
                    return self._json({"error": "not found"}, 404)
                f = (WEB / ("index.html" if path in ("/", "") else path.lstrip("/"))).resolve()
                if WEB not in f.parents and f != WEB / "index.html" or not f.is_file():
                    return self._send(404, b"not found", "text/plain")
                ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                if ctype.startswith("text/") or ctype.endswith("javascript"):
                    ctype += "; charset=utf-8"
                return self._send(200, f.read_bytes(), ctype)
            except Exception as exc:  # pragma: no cover - surfaced to the UI
                traceback.print_exc()
                return self._json({"error": str(exc)}, 500)

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                b = self._body()
                if path == "/api/run":
                    return self._json(app.run(int(b.get("situation", 1)), b.get("agent", "simple_reflex"), int(b.get("run_index", 0)),
                                              int(b.get("delivery", 1))))
                if path == "/api/compare":
                    return self._json(app.compare(int(b.get("situation", 1)), int(b.get("delivery", 1))))
                if path == "/api/train":
                    return self._json(app.train(int(b.get("episodes", DEFAULTS["episodes"])), int(b.get("seed", DEFAULTS["seed"]))))
                if path == "/api/test_policy":
                    return self._json(app.test_policy(int(b.get("runs", 200)), app._delivery(b.get("delivery", 1))))
                return self._json({"error": "not found"}, 404)
            except (ValueError, KeyError) as exc:
                return self._json({"error": str(exc)}, 400)
            except Exception as exc:  # pragma: no cover
                traceback.print_exc()
                return self._json({"error": str(exc)}, 500)

    return Handler


def serve(port: int = 8000, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    app = App()
    return ThreadingHTTPServer((host, port), make_handler(app))

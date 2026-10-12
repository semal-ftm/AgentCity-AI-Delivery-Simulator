# Agent City: Smart Food Delivery Agent Simulator

Agent City is an interactive 2D simulator for the Agent-Based Modeling course (Assignment 1). Seven AI agent architectures each solve the same food-delivery problem in a small simulated city. You can watch one agent at a time observe the city, reason, choose a route and ride it. You can then switch to another agent in the same situation, or compare all seven agents side by side.

> **All data is simulated.** The city, roads, orders, traffic and prices are fictional. The project uses no real maps, no external APIs and no LLM.

## Quick start

You need Python 3.10 or newer. The simulator itself uses only the Python standard library.

```bash
cd smart_food_delivery
python app.py                  # opens http://127.0.0.1:8000 in your browser
```

Optional extras:

```bash
pip install -r requirements.txt        # matplotlib (report charts) + pytest
python run_experiments.py              # 7 agents x 3 situations -> results/ (CSV, JSON, Markdown, PNG charts, SVG diagrams)
python -m pytest                       # 32 automated tests
python app.py --port 8080 --no-browser
```

The dashboard works offline. Without an internet connection the browser only falls back to system fonts.

## What the dashboard shows

The dashboard shows only what the assignment asks for.

| Screen | What it shows (assignment requirement) |
|---|---|
| **Simulate** | Choose one of the **three test situations** and one of the **seven agents**, then Start, Pause/Resume, Reset, Previous step or Next step. The 3D city shows the four routes, the traffic and the weather, and the rider rides the chosen route. The right panel has two tabs. **🧠 Agent reasoning** shows the agent's decision-making behaviour step by step: observe, reason, decide, act, respond, result. **📜 Rules** lists the selected agent's complete rulebook (for example R1–R4 for Simple Reflex, S1–S4 and M1–M3 for Model-Based, G1–G4 for Goal-Based, and the context classes and strategies for Contextual). It doesn't move with the simulation, so you can read it at your own pace, and after the agent decides, the rules it actually used are marked ✓. **💾 Memory** (Learning agent only) shows its real learned memory for the current situation, how this delivery changed it, the first and latest practice deliveries, and a customer feedback history; the Learning agent's result card has a star rating to add to that history (the ratings are a record only and do not change the learned values). A **🌙 Dark mode / ☀️ Light mode** button in the top bar switches the background, and the choice is remembered. **🧭 Why this route?** shows, once the agent has decided, which route it took and on what basis, why every other route was rejected or never considered, what each route would actually have delivered (200 simulated runs), and whether the choice was the best one in hindsight. |
| **Results & comparison** | **Results for the three test cases** (route, basis of the decision, time, cost, safety, on-time %, reward), charts, the route each agent chose in each situation, a **comparison** of how the agents behaved differently, and the **conclusion** on the most suitable agent. Also shows the learning agent's reward curve, which is evidence that it learns from feedback. |
| **Architecture diagrams** | **One architecture diagram per agent** (Input/Perception → Decision process → Action → Environment, plus rules, internal state, goal, utility, learning/feedback, subgoals or context), with a short explanation. |

## The seven agents

| # | Agent | How it decides (file) |
|---|---|---|
| 1 | Simple Reflex | Applies IF-THEN rules R1–R4 to the **current** percept only. It remembers nothing, so a route whose sensor is offline is invisible to it. (`agents/simple_reflex.py`) |
| 2 | Model-Based Reflex | Keeps an **internal state** (traffic per route with the time it was seen, flooding, order status). Missing reports are remembered and age. Its rules run on that state. (`agents/model_based.py`) |
| 3 | Goal-Based | **Goal:** arrive by the deadline. It predicts each plan, tests it against the goal, and takes the first plan that passes. If none can pass, it says so, falls back to the plan that is least late, and notifies the customer. (`agents/goal_based.py`) |
| 4 | Utility-Based | Scores every route as **U = 0.40·Time + 0.30·Safety + 0.20·Cost + 0.10·Distance**, with each score on a 0–100 scale, and picks the highest. (`agents/utility_based.py`) |
| 5 | Learning | **Tabular Q-learning** from delivery rewards, using ε-greedy training and greedy testing. (`agents/learning.py`) |
| 6 | Hierarchical | Splits the delivery into **8 subtasks with dependencies**, run by a scheduler. Each task moves pending → running → completed. (`agents/hierarchical.py`) |
| 7 | Contextual | Collects context (weather, night, urgency, congestion, sensor gaps, food type, slack), classifies the situation, and **switches strategy**: cheapest, fastest, or safety floor first. (`agents/contextual.py`) |

## The three test situations

| | Weather | Traffic | Deadline | Special |
|---|---|---|---|---|
| S1 Normal traffic + good weather | clear, 14:00 | normal everywhere | 35 min | – |
| S2 Heavy traffic + multiple routes | clear, 18:00 rush hour | downtown and expressway heavy; ring road light, but its sensor is offline | 30 min | partial sensor data |
| S3 Heavy traffic + rain + urgent | rain, 21:30 night | downtown heavy; old-town lanes flood | 23 min | urgent, hot soup |

## Results

These come from seed 42, with 200 simulated runs per decision. `python run_experiments.py` produces the same numbers.

| Agent | S1 route | S2 route | S3 route | Mean reward |
|---|---|---|---|---|
| Simple Reflex | A | C | B (on time 18.5%) | +0.43 |
| Model-Based Reflex | A | B | D | +3.72 |
| Goal-Based | A | C | D | +3.20 |
| Utility-Based | A | B | B (on time 18.5%) | +0.94 |
| Learning | B | B | D | **+3.90** |
| Hierarchical | A | B | D | +3.72 |
| Contextual | A | B | D | +3.72 |

The full analysis and the conclusion are in [docs/REPORT.md](docs/REPORT.md). Viva preparation is in [docs/VIVA.md](docs/VIVA.md).

## Technology and why it was chosen

- **Python engine and agents** (standard library only). The road network, simulators and all seven agents are plain Python classes, so they are easy to read in a viva and easy to test.
- **Standard-library HTTP server** (`server.py`). It needs no installation and starts with one command. It exposes a small JSON API.
- **Isometric low-poly 3D city with three.js** (stored offline in `web/vendor/`), plus SVG charts and diagrams, with no framework or build step. three.js gives the toy-city look (towers, warehouses, houses, trees, street lamps, zebra crossings, moving cars, shadows, rain at night) and a camera that follows the rider. A UI framework such as React would add a build step without improving the simulation view.
- **One source of truth.** The map is drawn from the backend road-network graph, and the rider animates the exact edge timings that the environment executed. Every explanation is read from the agent's own trace.

## Project structure

```
smart_food_delivery/
├── app.py                 start the dashboard
├── server.py              JSON API + static files (standard library)
├── run_experiments.py     batch results, charts and diagrams for the report
├── engine/                simulation engine
│   ├── city.py            road network graph, landmarks, routes A-D
│   ├── world.py           traffic simulator, weather simulator, route evaluation engine
│   ├── scenarios.py       scenario manager (3 situations + random training situations)
│   ├── environment.py     percepts, edge-by-edge execution, reward
│   └── metrics.py         200-run evaluation with common random numbers
├── agents/                the 7 architectures + base class and trace
├── sim/                   runner (6-phase timeline), comparison, SVG diagrams
├── web/                   index.html, css/, js/ (city3d.js, panel.js, charts.js, app.js), vendor/three.min.js
├── data/                  scenarios.json (editable), q_table.json (learned)
├── results/               generated tables, figures/ and diagrams/
├── tests/                 32 pytest tests
└── docs/                  REPORT.md, ARCHITECTURE.md, VIVA.md
```

The previous implementation was archived to `../backup_previous_implementation_2026-10-11.zip` before this rebuild.

## Optional second delivery (new source and destination)

On the Simulate screen, **📍 Source → destination** lets you switch from **Delivery 1 (default, west to east)** to **Delivery 2 (new, top to bottom)**: Food Street Kitchen in the north to Johar Town in the south, with its own routes A–D. All seven agents, the three situations, the reasoning tabs and the Results page work for both. Delivery 2 deadlines are 3 minutes later (longer trip), and the Learning agent has a separate memory for it (`data/q_table_delivery2.json`). `python run_experiments.py` writes its results to `results/delivery2/`; delivery 1's results do not change.

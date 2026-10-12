# Viva preparation

Short answers to likely questions. Every number refers to seed 42 and 200 runs (`python run_experiments.py`).

## General

**What is an agent?** Something that perceives its environment through sensors and acts on it through actuators to achieve its objectives. Here the agent receives traffic feeds, weather and the order, and its action is the route the rider takes (plus whether to notify the customer).

**What is the environment like?** It is *partially observable* (sensors can be offline, and incidents and random delays are hidden), *stochastic* (travel times vary and incidents can happen), *episodic* (one delivery is one decision), *static while deciding*, *discrete* in actions (4 routes) and *single-agent*.

**What is the performance measure?** +10 if on time, otherwise −0.8 per late minute (−5 more if urgent); then −0.3 × cost, −15 × (1 − safety), and −10 per incident. It is the same for every agent and is also the learning agent's reward.

**Why 200 runs per decision?** The environment is random. One run could be lucky or unlucky, so we report the average over 200 runs. All agents use the same 200 random seeds, so equal decisions give equal results.

## Agent by agent

| Agent | One-line answer | Weakness seen in our tests |
|---|---|---|
| Simple Reflex | IF-THEN rules on the current percept; no memory | S2: cannot see route B (sensor offline) → slower C. S3: no notion of a deadline → B, late 81.5% of the time |
| Model-Based Reflex | Rules on an internal state that remembers and ages old reports and models flooding | Memory can be stale; it has no explicit goal |
| Goal-Based | Predict each plan, take the first that satisfies arrival ≤ deadline; fallback + notify if impossible | Satisfices: in S2 it accepts C (on time) and never checks the better B |
| Utility-Based | U = 0.4·Time + 0.3·Safety + 0.2·Cost + 0.1·Distance (0–100 scores), choose the maximum | Fixed weights: in S3 it picks the cheaper, safer B even though its own forecast says it will be late |
| Learning | Q-learning, Q ← Q + α(r − Q), ε-greedy training, greedy testing | Needs 1500 simulated deliveries; knows nothing about unseen states |
| Hierarchical | 8 subtasks with dependencies run by a scheduler; traffic and weather checks filter routes, then select-route decides | Fixed decomposition; hard filters may discard good options |
| Contextual | Classify the context (calm, congested, urgent, storm, storm + urgent) and switch strategy | Context classes and strategies are hand-designed |

## Tricky questions

**Why does the Goal-Based agent choose C in S2 when B is better?** A goal-based agent only needs *a* plan that reaches the goal. It searches shortest-first, C passes the goal test (24.5 ≤ 30 min), and it stops. Choosing the *best* plan needs a utility, which is exactly what the utility-based agent adds.

**Why does the Utility-Based agent get S3 wrong?** Its weights are fixed for all situations, and the deadline is only indirectly in "time". B scores 81.8 against D's 77.9, because B is cheaper and safer, even though B is predicted at 24.4 min against a 23-min deadline. An urgent late delivery costs a lot of reward. The contextual agent fixes this by changing its objective in that context.

**Is the Learning agent's result hard-coded?** No. The Q-table starts at 0. It is filled only from rewards of simulated deliveries during training (the learning curve on the Results & comparison page shows the reward rising from −1.78 to +0.65). Retraining with seeds 7 or 123 gives the same final policy. A test checks that the learned route equals the route with the best measured reward in each situation.

**Why α = 1/n and γ = 0?** Each delivery has one decision, so the next state is terminal and max Q(s′) = 0. Rewards are noisy (random delays, incidents), so a running mean (α = 1/n, at least 0.02) estimates the expected reward better than a constant α, which over-reacts to single incidents.

**What does "internal state" contain?** For each route: the believed traffic, the clock time it was seen, its age and whether it was observed or remembered. Also the weather, the flooded routes, the order status and the current route. In S2 the state says "B light, remembered from 17:50 (10 min old)".

**How is the hierarchy enforced?** The scheduler only starts a task whose dependencies are all completed. Calling a task early raises an error, and a test checks this. Tasks 6–8 (pick up, execute, confirm) run during the delivery and update live on the dashboard.

**What makes the contextual agent different from the utility agent?** The utility agent always optimises the same weighted formula. The contextual agent first decides what kind of situation it is in, and then changes *what* it optimises (cost, safety or arrival time) and *which constraints* apply (a safety floor, a stale-data margin, spill-sensitive food).

**Which agent is best?** By reward, the Learning agent (+3.90 mean), but only after training. Without training, the Contextual agent is the most suitable: it matches the best result in S2 and S3, and it is explainable. Our recommendation is a contextual agent whose strategies are tuned offline by learning.

**How do you know the animation matches the results?** The rider plays back execution #k of the 200 seeded runs. A test checks that the animated trip equals a fresh execution with the same seed, and that every segment is an edge of the road graph.

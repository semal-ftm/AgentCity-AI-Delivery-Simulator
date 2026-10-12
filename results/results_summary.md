# Results (seed 42, 200 simulated runs per decision, learning agent trained for 1500 episodes)

All data is simulated. Times in minutes from order placement; cost in simulated cost units (CU).

## Situation 1: Normal traffic + good weather

Deadline 35 min.

| Agent | Route | Forecast | Mean time | Cost | Safety | On time | Incidents | Reward |
|---|---|---|---|---|---|---|---|---|
| Simple Reflex Agent | A | - | 17.68 | 2.75 | 0.798 | 100.0% | 1.5% | +5.99 |
| Model-Based Reflex Agent | A | 17.6 | 17.68 | 2.75 | 0.798 | 100.0% | 1.5% | +5.99 |
| Goal-Based Agent | A | 17.6 | 17.68 | 2.75 | 0.798 | 100.0% | 1.5% | +5.99 |
| Utility-Based Agent | A | 17.6 | 17.68 | 2.75 | 0.798 | 100.0% | 1.5% | +5.99 |
| Learning Agent | B | - | 22.44 | 4.11 | 0.868 | 100.0% | 2.5% | +6.55 |
| Hierarchical Agent | A | 17.6 | 17.68 | 2.75 | 0.798 | 100.0% | 1.5% | +5.99 |
| Contextual Agent | A | 17.6 | 17.68 | 2.75 | 0.798 | 100.0% | 1.5% | +5.99 |

## Situation 2: Heavy traffic + multiple routes

Deadline 30 min.

| Agent | Route | Forecast | Mean time | Cost | Safety | On time | Incidents | Reward |
|---|---|---|---|---|---|---|---|---|
| Simple Reflex Agent | C | - | 24.69 | 3.82 | 0.763 | 98.5% | 4.0% | +4.73 |
| Model-Based Reflex Agent | B | 22.1 | 22.49 | 3.81 | 0.865 | 99.5% | 5.0% | +6.27 |
| Goal-Based Agent | C | 24.5 | 24.69 | 3.82 | 0.763 | 98.5% | 4.0% | +4.73 |
| Utility-Based Agent | B | 22.1 | 22.49 | 3.81 | 0.865 | 99.5% | 5.0% | +6.27 |
| Learning Agent | B | - | 22.49 | 3.81 | 0.865 | 99.5% | 5.0% | +6.27 |
| Hierarchical Agent | B | 22.1 | 22.49 | 3.81 | 0.865 | 99.5% | 5.0% | +6.27 |
| Contextual Agent | B | 22.1 | 22.49 | 3.81 | 0.865 | 99.5% | 5.0% | +6.27 |

## Situation 3: Heavy traffic + rain + urgent delivery

Deadline 23 min (urgent).

| Agent | Route | Forecast | Mean time | Cost | Safety | On time | Incidents | Reward |
|---|---|---|---|---|---|---|---|---|
| Simple Reflex Agent | B | - | 24.66 | 4.59 | 0.752 | 18.5% | 7.0% | -9.44 |
| Model-Based Reflex Agent | D | 20.9 | 21.53 | 7.36 | 0.654 | 84.5% | 10.5% | -1.11 |
| Goal-Based Agent | D | 20.9 | 21.53 | 7.36 | 0.654 | 84.5% | 10.5% | -1.11 |
| Utility-Based Agent | B | 24.4 | 24.66 | 4.59 | 0.752 | 18.5% | 7.0% | -9.44 |
| Learning Agent | D | - | 21.53 | 7.36 | 0.654 | 84.5% | 10.5% | -1.11 |
| Hierarchical Agent | D | 20.9 | 21.53 | 7.36 | 0.654 | 84.5% | 10.5% | -1.11 |
| Contextual Agent | D | 20.9 | 21.53 | 7.36 | 0.654 | 84.5% | 10.5% | -1.11 |

## Mean reward over the three situations

| Agent | S1 | S2 | S3 | Mean |
|---|---|---|---|---|
| Simple Reflex Agent | +5.99 | +4.73 | -9.44 | **+0.43** |
| Model-Based Reflex Agent | +5.99 | +6.27 | -1.11 | **+3.72** |
| Goal-Based Agent | +5.99 | +4.73 | -1.11 | **+3.20** |
| Utility-Based Agent | +5.99 | +6.27 | -9.44 | **+0.94** |
| Learning Agent | +6.55 | +6.27 | -1.11 | **+3.90** |
| Hierarchical Agent | +5.99 | +6.27 | -1.11 | **+3.72** |
| Contextual Agent | +5.99 | +6.27 | -1.11 | **+3.72** |

Learning agent: mean reward -1.78 over the first 150 training episodes, 0.65 over the last 150.

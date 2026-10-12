# Delivery 2 results: Food Street Kitchen (north) -> Johar Town (south) (top to bottom)

Same three situations as delivery 1; this trip is longer, so each deadline is 3 minutes later. Seed 42, 200 runs per decision; the Learning agent has its own memory for this delivery (mean training reward 1.41 -> 2.94).

## Situation 1: Normal traffic + good weather (deadline 38 min)

| Agent | Route | Mean time | Cost | Safety | On time | Reward |
|---|---|---|---|---|---|---|
| Simple Reflex Agent | A | 21.07 | 3.3 | 0.804 | 100.0% | +5.52 |
| Model-Based Reflex Agent | A | 21.07 | 3.3 | 0.804 | 100.0% | +5.52 |
| Goal-Based Agent | A | 21.07 | 3.3 | 0.804 | 100.0% | +5.52 |
| Utility-Based Agent | A | 21.07 | 3.3 | 0.804 | 100.0% | +5.52 |
| Learning Agent | B | 21.56 | 3.77 | 0.854 | 100.0% | +6.28 |
| Hierarchical Agent | A | 21.07 | 3.3 | 0.804 | 100.0% | +5.52 |
| Contextual Agent | A | 21.07 | 3.3 | 0.804 | 100.0% | +5.52 |

## Situation 2: Heavy traffic + multiple routes (deadline 33 min)

| Agent | Route | Mean time | Cost | Safety | On time | Reward |
|---|---|---|---|---|---|---|
| Simple Reflex Agent | C | 23.33 | 3.34 | 0.781 | 100.0% | +5.16 |
| Model-Based Reflex Agent | B | 22.25 | 3.58 | 0.851 | 100.0% | +6.09 |
| Goal-Based Agent | A | 27.76 | 4.0 | 0.789 | 97.5% | +4.79 |
| Utility-Based Agent | B | 22.25 | 3.58 | 0.851 | 100.0% | +6.09 |
| Learning Agent | B | 22.25 | 3.58 | 0.851 | 100.0% | +6.09 |
| Hierarchical Agent | C | 23.33 | 3.34 | 0.781 | 100.0% | +5.16 |
| Contextual Agent | C | 23.33 | 3.34 | 0.781 | 100.0% | +5.16 |

## Situation 3: Heavy traffic + rain + urgent delivery (deadline 26 min)

| Agent | Route | Mean time | Cost | Safety | On time | Reward |
|---|---|---|---|---|---|---|
| Simple Reflex Agent | B | 23.73 | 4.25 | 0.74 | 91.5% | +2.72 |
| Model-Based Reflex Agent | D | 23.53 | 7.46 | 0.672 | 90.0% | +0.24 |
| Goal-Based Agent | B | 23.73 | 4.25 | 0.74 | 91.5% | +2.72 |
| Utility-Based Agent | B | 23.73 | 4.25 | 0.74 | 91.5% | +2.72 |
| Learning Agent | B | 23.73 | 4.25 | 0.74 | 91.5% | +2.72 |
| Hierarchical Agent | D | 23.53 | 7.46 | 0.672 | 90.0% | +0.24 |
| Contextual Agent | D | 23.53 | 7.46 | 0.672 | 90.0% | +0.24 |

## Mean reward over the three situations

| Agent | Mean reward |
|---|---|
| Simple Reflex Agent | +4.47 |
| Model-Based Reflex Agent | +3.95 |
| Goal-Based Agent | +4.34 |
| Utility-Based Agent | +4.78 |
| Learning Agent | +5.03 |
| Hierarchical Agent | +3.64 |
| Contextual Agent | +3.64 |

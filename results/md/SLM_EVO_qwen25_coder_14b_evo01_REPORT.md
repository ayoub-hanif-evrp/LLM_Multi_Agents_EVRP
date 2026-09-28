# SLM-Evo — `evo01`

**Model:** `qwen2.5-coder:14b` | **parent:** `results/md/artifacts/mcb_v1/FEASIBLE_SYNTHESIZED_SOLVER_V0_qwen14b_seed33/solver.py` (`3f427deb2d9bf534`)

**milestone_hit:** `True` (`c103C5`)
**best_hash:** `a1809c66b508a98b`
**panel vehicles_sum:** `17` (parent `20`)
**all_c5:** `12/12` vehicles=`53` (parent `60`)
**generations:** `8` | **llm_calls:** `91` | **wall_s:** `2617.6`
**freeze:** `results/md/artifacts/slm_evo/VEHICLE_WIN_a1809c66b508a98b`

## Milestone mechanism

First panel instance with **&lt;5 vehicles** while remaining panel-feasible: `c103C5` (**5 → 3**). Also `r105C5` **5 → 4**.

Accepted patch (gen 7, focus=`SEARCH`, role=`search`, candidate `g7_p0_search_7`):

- **Hypothesis:** Improve the EVRPTW solver to minimize the number of vehicles and then the total distance while preserving feasibility.
- **Ops:** `ADD calculate_total_distance`, `REPLACE solve`

Mechanism (no optimality claim):

1. Sort customers by demand (descending) before building singleton routes.
2. Keep parent-style station insert on battery fail.
3. **Greedy route merge:** try appending a route’s body onto an existing merged route if `propagate_route` stays battery-feasible.
4. Helper `calculate_total_distance` used only to sort merged routes.

Deployment remains **zero LLM calls** after freeze.

## Panel detail (dev G4 C5)

| Instance | Parent veh | Win veh |
| --- | ---: | ---: |
| c101C5 | 5 | 5 |
| c103C5 | 5 | **3** |
| r104C5 | 5 | 5 |
| r105C5 | 5 | **4** |

## Generations (accepted)

| Gen | Focus | Accepted |
| ---: | --- | ---: |
| 0–6 | ROUTING/CHARGING/SEARCH cycle | 0/10 each |
| 7 | SEARCH | **1/10** → milestone stop |

MCB V1 unchanged.

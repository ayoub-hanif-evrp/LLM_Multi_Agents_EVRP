# P1_MINIMAL_COOPERATIVE_SOLVER — first experiment report

**Protocol:** `P1_MINIMAL_COOPERATIVE_SOLVER`  
**Model:** `qwen2.5-coder:7b`  
**Agents:** exactly 5 (Architect, Routing, Charging, Search, Critic)  
**Workspace:** empty at start (`workspace/discovery_p1_minimal/qwen25_coder_7b/`)  
**Stopped:** `PARTIAL_G4_3` (success criterion met: G4 ≥ 1/4)

P0 results remain archived and unchanged under `results/md/archive_p0_clean/`.

---

## Gate results

| Gate | Result | Detail |
| --- | --- | --- |
| G0 | **PASS** | software contract ok |
| G1 | **PASS** | one-customer no-charge feasible |
| G2 | **PASS** | one-customer needs-charge feasible |
| G3 | **PASS** | two-customer feasible |
| G4 | **3/4** | c101C5, c103C5, r104C5 feasible; r105C5 WINDOW fail |

```text
G0: PASS
G1: PASS
G2: PASS
G3: PASS

G4: 3/4

LLM calls: 10
prompt tokens: 9906
completion tokens: 1525
wall time: 42.1 s
```

---

## Artifacts

- **final solver.py:** `workspace/discovery_p1_minimal/qwen25_coder_7b/current/solver.py`
- **FEASIBLE_SOLVER_V0:** `workspace/discovery_p1_minimal/qwen25_coder_7b/FEASIBLE_SOLVER_V0/`
- **inspection copy:** `results/md/artifacts/p1_minimal/solver.py`
- **raw JSON:** `results/md/tables/raw_autolab/discovery_p1_minimal_qwen25_coder_7b.json`

---

## First successful routes (agent-invented)

**G1**
```text
[['D0', 'C1', 'D0']]
```

**G2** (station inserted by generated repair logic)
```text
[['D0', 'C1', 'S0', 'D0']]
```

**G3**
```text
[['D0', 'C1', 'D0'], ['D0', 'C2', 'D0']]
```

**G4 examples (feasible)**
```text
c101C5: one dedicated route per customer (5 vehicles)
c103C5: one dedicated route per customer (5 vehicles)
r104C5: includes station on one route, e.g. ['D0', 'C71', 'S3', 'D0'], ...
r105C5: FAIL (WINDOW)
```

---

## Which agent changes produced each gate

- **G0:** Architect plan → Routing write → Charging write → Search write (gen0). No coding-repair needed on the successful run.
- **G1:** passed on gen0 solver (no further edits).
- **G2:** passed on gen0 solver (Charging’s gen0 contribution already included `propagate_route` + station insertion).
- **G3:** passed on gen0 solver.
- **G4:** 3/4 already feasible with the same solver; Search made 3 algo_fix attempts on the failing instance (`r105C5`) without clearing the WINDOW fault.

---

## What the agents invented

A small constructive solver:

1. one dedicated `depot → customer → depot` route per customer;
2. if `propagate_route` shows any `battery_arrival < 0`, try inserting each `station_id` before the failing index until the route is battery-feasible.

No GA/ALNS/VNS. No framework fallback solver. Optimization remains locked (vehicle count not minimized).

---

## Next (not done yet)

- Do **not** run the 4–5 model comparison until this protocol is frozen as `PAPER_PROTOCOL_V1`.
- Optional: continue BUILD only to push G4 to 4/4 (WINDOW on `r105C5`), still without optimization unlock.
- Only after a frozen feasible solver: unlock optimization (vehicles, then distance) and evolutionary infrastructure.

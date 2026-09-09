# P1.1 WINDOW fix (G4 → 4/4)

**Protocol:** keep P1 five-agent loop; no islands / optimization / handcrafted solver.  
**Model:** `qwen2.5-coder:7b`  
**Seed:** P1 `FEASIBLE_SOLVER_V0` (3/4 panel)

## Protocol changes shipped

1. **G4 PASS requires 4/4** (progress reported separately as `G4_progress`).
2. **Final full-panel re-eval** of the same `solver.py` on all four instances.
3. **WINDOW diagnostics:** route, violating node, previous node, arrival, due, lateness.
4. **Critic → ROUTING/CHARGING** for WINDOW (not Search).
5. **NO_OP detection** (SHA-256): identical code → switch specialist; stop if stuck.

## Result (Qwen P1.1)

| Gate | Result |
| --- | --- |
| G0–G3 | PASS (seed) |
| G4 progress | **3/4** |
| G4 PASS (4/4 required) | **False** |

```text
c101C5 OK
c103C5 OK
r104C5 OK
r105C5 WINDOW  (still)

LLM calls: 21
prompt tokens: 35421
completion tokens: 6536
wall: 182.4 s
stopped: PARTIAL_G4_3
```

Fault on `r105C5` remains:

```text
route: D0 → C78 → S1 → D0
violating: D0 (return)
previous: S1
arrival ≈ 235.1  due = 230  lateness ≈ 5.1
```

Agents produced many **NO_OP** responses and a few non-identical edits that did not clear the WINDOW. Run stopped via `stuck_noop` / `give_up_noop` rather than re-executing the same solver endlessly.

**Not frozen as FEASIBLE_SOLVER_V0 (4/4).** No C5 generalization panel run. Optimization still locked.

## Assessment

P1.1 infrastructure fixes are in place and healthier. **G4 = 4/4 was not achieved** with Qwen 7B under this budget — the open scientific problem is real WINDOW repair on `r105C5`, not imports/syntax.

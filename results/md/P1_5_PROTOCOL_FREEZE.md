# P1.5 — Runtime-Safe Synthesis (FROZEN)

**Frozen before `synth03`.** Final software-integrity layer. No further P1.6+ integrity patches.

## Invariant

> A coding mistake may fail a trial, but it may never destroy the latest runnable solver or consume an algorithmic research cycle before receiving bounded mechanical repair.

## Validation order

```text
candidate
→ AST parse / compile
→ hardcoded instance-ID audit
→ sandbox execution on current gate probe
→ commit only if runtime-valid
```

## Mechanical repair

- Same coding role only (`routing` / `charging` / `search`)
- Max **2** attempts
- Exact SYNTAX / RUNTIME / GENERALITY feedback
- **No** Architect, **No** Critic
- Counts toward total LLM budget
- After exhaustion → `CODING_FAILURE` (stop)

## Hardcoded IDs

Reject string literals that equal `instance.depot_id` / `customer_ids` / `station_ids`.

```python
"S0"           # INVALID if that station exists on the probe
instance.station_ids[0]  # VALID
```

## Failure taxonomy

`FORMAT | SYNTAX | RUNTIME | GENERALITY | FEASIBILITY | OPTIMIZATION | NO_OP`

## Not changed

EVRPTW prompts, Critic intelligence, curriculum G0–G4, optimization (still locked), LLM budget ceiling.

## Experiment label

| Run | Protocol |
| --- | --- |
| synth01 | P1-B corruption (permanent) |
| synth02 | P1.4 AST-only |
| **synth03** | **P1.5 runtime-safe** |

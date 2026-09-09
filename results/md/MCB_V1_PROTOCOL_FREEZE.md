# MINIMAL_COOPERATIVE_BUILD_V1 — Protocol freeze (**PERMANENT**)

**Frozen after `synth04`.** Do not create MCB V2. Do not add EVRPTW hints, charging recipes, or station-placement guidance based on observed failures.

## Status

| Item | Verdict |
| --- | --- |
| MCB V1 implementation | accepted |
| Targeted tests | 18/18 |
| First valid measurement | DeepSeek `synth04` — G2 BATTERY |
| Protocol modifications | **STOP** |

## Intent

Test **five cooperating agents** synthesizing an EVRPTW solver from an empty workspace.

## Draft vs committed

```text
committed/solver.py  = last runtime-valid solver (never destroyed by a bad draft)
draft/solver.py      = current specialist proposal (may be runtime-invalid)
```

## Team mechanical path

```text
Specialist → draft
AST (specialist ≤1 syntax repair)
Search/Integration sees draft + exact traceback (≤2 repairs)
runtime-valid? → COMMIT
else → CODING_FAILURE (after team path exhausted)
```

## Experimental policy (post-freeze)

1. **Screening:** one empty-workspace run per model under identical MCB V1.
2. **Do not** rerun a model until success; do not tweak prompts between models.
3. Later: multi-seed repeats (e.g. seeds 11/22/33/44/55) for paper statistics.
4. Optimization remains **locked** until a from-scratch solver reaches G4 and C5 eval.

## Permanent negative datapoint

```text
DeepSeek-Coder 6.7B — empty-workspace synthesis — synth04 — G2 BATTERY
```

## Labels

| Run | Protocol | Note |
| --- | --- | --- |
| synth01–03 | prior | permanent lab-history records |
| synth04 | MCB V1 | DeepSeek clean negative result |
| screen01 | MCB V1 | cross-model screening |

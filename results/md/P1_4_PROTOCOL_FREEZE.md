# P1.4 — Code-Integrity-Safe Synthesis (frozen)

**Frozen before synth02.** No EVRPTW prompt/algorithm/curriculum changes vs P1.

## Invariant

> No syntactically invalid model output can overwrite the last syntactically valid `solver.py`.

## Mechanics

1. Coding roles only (`routing`, `charging`, `search`) may produce Python.
2. `architect` / `critic` are reasoning-only (no file-write path in P1.4).
3. Candidate → temp/checkpoint → `ast.parse` + `compile` → commit or reject.
4. On reject: up to **2** same-role syntax repairs with the exact SyntaxError; then stop that edit.
5. Checkpoints under `workspace/.../checkpoints/` (`*_raw.txt`, `*_candidate.py`, `*_committed.py`).

## Experiment labels

| Run | Protocol | Meaning |
| --- | --- | --- |
| `synth01` | P1-B (pre-integrity) | Permanent corruption post-mortem — **do not reuse** |
| `synth02` | **P1.4** | Empty-workspace DeepSeek under integrity gate |

## Success levels (unchanged from Experiment B)

B0…B4 / Strong B as predefined.

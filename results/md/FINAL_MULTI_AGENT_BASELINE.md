# FINAL — Five-agent MCB V1 vs Single-agent matched baseline

Model: `qwen2.5-coder:7b`. Seeds `11/22/33/44/55`.

**Budget semantics:** paired token-ceiling baseline with **call-boundary overshoot**.
The final in-flight LLM call may finish after the ceiling; tables report **actual** tokens.
This is soft-ceiling matching, not a hard abort mid-generation.

**Prompt parity:** single-agent prompt carries the **union** of fixed API/domain guidance
(routing + charging physics + solve contract) without role decomposition.
Active SA run prefix: `single_qwen_parity_seed`.

**Outcome B:** The specialized five-agent architecture introduced communication/coordination overhead and did not outperform simpler self-refinement under matched inference.

| Metric | Five-agent Qwen MCB V1 | Single-agent Qwen |
| --- | ---: | ---: |
| n | 5 | 5 |
| G1 success | 4/5 | 5/5 |
| G2 success | 3/5 | 4/5 |
| G3 success | 3/5 | 4/5 |
| reached G4 | 3/5 | 4/5 |
| G4 4/4 | 0/5 | 1/5 |
| mean G4 feasible count | 1.6 | 2 |
| median calls | 11 | 7 |
| median tokens | 18207 | 19383 |
| runtime-failure rate | 1/5 | 0/5 |
| feasibility-failure rate | 4/5 | 4/5 |
| NO_OP rate | 0/5 | 3/5 |

## Per-seed paired

| Seed | Five-agent highest | Single-agent highest | Five tokens | Single tokens | Overshoot |
| --- | --- | --- | ---: | ---: | ---: |
| 11 | G3 | G4 | 18179 | 6264 | 0 |
| 22 | G3 | G4_partial_2 | 39157 | 30686 | 0 |
| 33 | G3 | G4_partial_3 | 23579 | 22051 | 0 |
| 44 | none | G1 | 6205 | 6432 | 227 |
| 55 | G1 | G4_partial_1 | 18207 | 19383 | 1176 |

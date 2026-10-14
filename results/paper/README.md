# Paper results

These tables contain only the runs produced by `scripts/run_five_agent.py`, `scripts/run_single_agent.py`, and `scripts/run_evolution.py` in this repository. Historical development runs are not included.

## 1. Five-agent synthesis by model

| Model | Seeds | Executable | Routing | Charging | Multi-customer | C5 development | C5 development+confirmation | LLM calls | Tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| codellama:7b | 4 | 0/4 | 0/4 | 0/4 | 0/4 | 0/4 | 0/4 | 320 | 2040977 |
| None | 1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0 | 0 |
| deepseek-coder:6.7b | 5 | 4/5 | 1/5 | 0/5 | 0/5 | 0/5 | 0/5 | 400 | 1746430 |
| qwen2.5-coder:14b | 10 | 10/10 | 9/10 | 3/10 | 2/10 | 0/10 | 0/10 | 800 | 3722539 |
| qwen2.5-coder:7b | 10 | 8/10 | 6/10 | 2/10 | 1/10 | 0/10 | 0/10 | 756 | 3220088 |
| qwen3-coder:30b | 5 | 5/5 | 5/5 | 4/5 | 4/5 | 0/5 | 0/5 | 400 | 2269201 |

## 2. Five-agent Qwen 7B vs single-agent Qwen 7B

| System | Seeds | Executable | Routing | Charging | Multi-customer | C5 development | C5 development+confirmation | Tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| five-agent Qwen 7B | 10 | 8/10 | 6/10 | 2/10 | 1/10 | 0/10 | 0/10 | 3220088 |
| single-agent Qwen 7B | 10 | 7/10 | 6/10 | 2/10 | 1/10 | 0/10 | 0/10 | 3016471 |

Paired seeds: 10. Stage-depth wins/ties/losses (five-agent vs single-agent): 5/2/3.
G4-feasible-count wins/ties/losses: 0/10/0.
Exact two-sided sign test on non-tied stage depths: p=0.7266. This comparison does not establish that one architecture is superior.

Single-agent token ceilings are the paired five-agent token totals. Call-boundary overshoot is recorded on each single-agent row as `token_overshoot`.

## 3. Qwen 7B vs Qwen 14B (five-agent)

| Model | Seeds | C5 development | C5 development+confirmation | LLM calls | Tokens |
| --- | --- | --- | --- | --- | --- |
| Qwen 7B | 10 | 0/10 | 0/10 | 756 | 3220088 |
| Qwen 14B | 10 | 0/10 | 0/10 | 800 | 3722539 |

## 4. Solver evolution

| Seed | Improved | C5 development+confirmation | Vehicles | Distance | Calls | Hash | Runtime s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| — | — | — | — | — | — | — | — |

Valid improvements kept: 0.

Evolution did not start: no valid synthesized solver to evolve.

## 5. Final held-out and scale evaluation

no fully feasible synthesized solver.
no fully feasible evolved solver.
No frozen solver was evaluated. Held-out instances were not used to adapt any solver.

## 6. Failure categories

| Category | Count |
| --- | --- |
| SUCCESS | 0 |
| SYNTAX | 1 |
| RUNTIME | 22 |
| TIMEOUT | 0 |
| DEPOT | 3 |
| VISIT | 2 |
| CAPACITY | 0 |
| WINDOW | 5 |
| BATTERY | 10 |
| CHARGE_POLICY | 0 |
| GENERALITY | 0 |
| BUDGET | 2 |

## Best valid generated solver

No run produced a solver that is fully feasible on every non-held-out 5-customer instance.

## 7. Strong local anchor (Qwen3-Coder 30B) curriculum G4

From the frozen final campaign (tag `final-protocol-v1`):

| Seed | Deepest committed gate | curriculum_g4_best | posthoc_g4_score |
| --- | --- | ---: | ---: |
| 11 | multi_customer | 2 | (see raw JSON) |
| 22 | multi_customer | 1 | |
| 33 | routing | 0 | |
| 44 | multi_customer | 1 | |
| 55 | multi_customer | 1 | |

Best genuine curriculum G4 in this final campaign: **2/4** (seed 11).
No seed reached curriculum 4/4, so confirmation / evolution / held-out were correctly skipped.

Pilot (separate, selection only): Qwen3 seed 33 reached curriculum **3/4**; that justified selecting this anchor.

## Provenance

- Git tag: `final-protocol-v1` → `d83f9eb`
- Installed models: `results/paper/MODELS.txt`
- Each result JSON includes `git_commit`, `protocol_hash`, `config_hash` when stamped by the runners.

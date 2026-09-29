# Paper results

These tables contain only the runs produced by `scripts/run_five_agent.py`, `scripts/run_single_agent.py`, and `scripts/run_evolution.py` in this repository. Historical development runs are not included.

## 1. Five-agent synthesis by model

| Model | Seeds | Executable | Routing | Charging | Multi-customer | Schneider C5 panel | Non-held-out C5 | LLM calls | Tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| codellama:7b | 5 | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 | 36 | 150297 |
| deepseek-coder:6.7b | 5 | 1/5 | 1/5 | 0/5 | 0/5 | 0/5 | 0/5 | 79 | 257613 |
| qwen2.5-coder:14b | 10 | 9/10 | 8/10 | 0/10 | 0/10 | 0/10 | 0/10 | 210 | 668562 |
| qwen2.5-coder:7b | 10 | 8/10 | 5/10 | 0/10 | 0/10 | 0/10 | 0/10 | 197 | 590521 |

## 2. Five-agent Qwen 7B vs single-agent Qwen 7B

| System | Seeds | Executable | Routing | Charging | Multi-customer | Schneider C5 panel | Non-held-out C5 | Tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| five-agent Qwen 7B | 10 | 8/10 | 5/10 | 0/10 | 0/10 | 0/10 | 0/10 | 590521 |
| single-agent Qwen 7B | 10 | 7/10 | 6/10 | 0/10 | 0/10 | 0/10 | 0/10 | 212451 |

Paired seeds: 10. Stage-depth wins/ties/losses (five-agent vs single-agent): 2/7/1.
G4-feasible-count wins/ties/losses: 1/9/0.
Exact two-sided sign test on non-tied stage depths: p=1.0000. This comparison does not establish that one architecture is superior.

Single-agent token ceilings are the paired five-agent token totals. Call-boundary overshoot is recorded on each single-agent row as `token_overshoot`.

## 3. Qwen 7B vs Qwen 14B (five-agent)

| Model | Seeds | Schneider C5 panel | Non-held-out C5 | LLM calls | Tokens |
| --- | --- | --- | --- | --- | --- |
| Qwen 7B | 10 | 0/10 | 0/10 | 197 | 590521 |
| Qwen 14B | 10 | 0/10 | 0/10 | 210 | 668562 |

## 4. Solver evolution

| Seed | Improved | Non-held-out C5 | Vehicles | Distance | Calls | Hash | Runtime s |
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
| SYNTAX | 0 |
| RUNTIME | 18 |
| TIMEOUT | 1 |
| DEPOT | 3 |
| VISIT | 7 |
| CAPACITY | 0 |
| WINDOW | 0 |
| BATTERY | 11 |
| CHARGE_POLICY | 0 |
| GENERALITY | 0 |
| BUDGET | 0 |

## Best valid generated solver

No run produced a solver that is fully feasible on every non-held-out 5-customer instance.

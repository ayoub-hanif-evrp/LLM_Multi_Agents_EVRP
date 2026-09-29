# Paper results

These tables contain only the runs produced by `scripts/run_five_agent.py`, `scripts/run_single_agent.py`, and `scripts/run_evolution.py` in this repository. Historical development runs are not included.

## 1. Five-agent synthesis by model

| Model | Seeds | Executable | Routing | Charging | Multi-customer | Schneider C5 panel | All C5 | LLM calls | Tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| codellama:7b | 5 | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 | 400 | 1210349 |
| deepseek-coder:6.7b | 5 | 1/5 | 1/5 | 0/5 | 0/5 | 0/5 | 0/5 | 400 | 1135266 |
| qwen2.5-coder:14b | 10 | 5/10 | 4/10 | 1/10 | 1/10 | 0/10 | 0/10 | 800 | 2269988 |
| qwen2.5-coder:7b | 10 | 2/10 | 1/10 | 0/10 | 0/10 | 0/10 | 0/10 | 800 | 2108969 |

## 2. Five-agent Qwen 7B vs single-agent Qwen 7B

| System | Seeds | Executable | Routing | Charging | Multi-customer | Schneider C5 panel | All C5 | Tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| five-agent Qwen 7B | 10 | 2/10 | 1/10 | 0/10 | 0/10 | 0/10 | 0/10 | 2108969 |
| single-agent Qwen 7B | 10 | 9/10 | 8/10 | 0/10 | 0/10 | 0/10 | 0/10 | 2098768 |

Paired seeds: 10. Stage-depth wins/ties/losses (five-agent vs single-agent): 0/2/8.
G4-feasible-count wins/ties/losses: 0/8/2.
On non-tied seeds the exact two-sided sign test gives p=0.0078 in favor of the single-agent stage depth.

Single-agent token ceilings are the paired five-agent token totals. Call-boundary overshoot is recorded on each single-agent row as `token_overshoot`.

## 3. Qwen 7B vs Qwen 14B (five-agent)

| Model | Seeds | Schneider C5 panel | All C5 | LLM calls | Tokens |
| --- | --- | --- | --- | --- | --- |
| Qwen 7B | 10 | 0/10 | 0/10 | 800 | 2108969 |
| Qwen 14B | 10 | 0/10 | 0/10 | 800 | 2269988 |

## 4. Solver evolution

| Seed | Improved | All C5 | Vehicles | Distance | Calls | Hash | Runtime s |
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
| SYNTAX | 3 |
| RUNTIME | 26 |
| TIMEOUT | 1 |
| DEPOT | 2 |
| VISIT | 1 |
| CAPACITY | 0 |
| WINDOW | 0 |
| BATTERY | 7 |
| CHARGE_POLICY | 0 |
| GENERALITY | 0 |
| BUDGET | 0 |

## Best valid generated solver

No run produced a solver that is fully feasible on every non-held-out 5-customer instance.

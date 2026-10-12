# Paper results

These tables contain only the runs produced by `scripts/run_five_agent.py`, `scripts/run_single_agent.py`, and `scripts/run_evolution.py` in this repository. Historical development runs are not included.

## 1. Five-agent synthesis by model

| Model | Seeds | Executable | Routing | Charging | Multi-customer | C5 development | C5 development+confirmation | LLM calls | Tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| codellama:7b | 5 | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 | 400 | 1795752 |
| deepseek-coder:6.7b | 5 | 4/5 | 3/5 | 0/5 | 0/5 | 0/5 | 0/5 | 400 | 1432625 |
| qwen2.5-coder:14b | 10 | 10/10 | 10/10 | 4/10 | 3/10 | 0/10 | 0/10 | 800 | 2538326 |
| qwen2.5-coder:7b | 10 | 2/10 | 2/10 | 0/10 | 0/10 | 0/10 | 0/10 | 800 | 2700910 |

## 2. Five-agent Qwen 7B vs single-agent Qwen 7B

| System | Seeds | Executable | Routing | Charging | Multi-customer | C5 development | C5 development+confirmation | Tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| five-agent Qwen 7B | 10 | 2/10 | 2/10 | 0/10 | 0/10 | 0/10 | 0/10 | 2700910 |
| single-agent Qwen 7B | 10 | 2/10 | 1/10 | 0/10 | 0/10 | 0/10 | 0/10 | 2716978 |

Paired seeds: 10. Stage-depth wins/ties/losses (five-agent vs single-agent): 1/8/1.
G4-feasible-count wins/ties/losses: 0/9/1.
Exact two-sided sign test on non-tied stage depths: p=1.0000. This comparison does not establish that one architecture is superior.

Single-agent token ceilings are the paired five-agent token totals. Call-boundary overshoot is recorded on each single-agent row as `token_overshoot`.

## 3. Qwen 7B vs Qwen 14B (five-agent)

| Model | Seeds | C5 development | C5 development+confirmation | LLM calls | Tokens |
| --- | --- | --- | --- | --- | --- |
| Qwen 7B | 10 | 0/10 | 0/10 | 800 | 2700910 |
| Qwen 14B | 10 | 0/10 | 0/10 | 800 | 2538326 |

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
| SYNTAX | 0 |
| RUNTIME | 21 |
| TIMEOUT | 2 |
| DEPOT | 2 |
| VISIT | 3 |
| CAPACITY | 0 |
| WINDOW | 1 |
| BATTERY | 10 |
| CHARGE_POLICY | 0 |
| GENERALITY | 1 |
| BUDGET | 0 |

## Best valid generated solver

No run produced a solver that is fully feasible on every non-held-out 5-customer instance.

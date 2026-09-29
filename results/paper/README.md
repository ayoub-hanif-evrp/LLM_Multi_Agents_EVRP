# Paper results

These tables contain only the runs produced by `scripts/run_five_agent.py`, `scripts/run_single_agent.py`, and `scripts/run_evolution.py` in this repository. Historical development runs are not included.

## 1. Five-agent synthesis by model

| Model | Seeds | Executable | Routing | Charging | Multi-customer | Schneider C5 panel | All C5 | LLM calls | Tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| codellama:7b | 5 | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 | 400 | 1275660 |
| deepseek-coder:6.7b | 5 | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 | 400 | 1497989 |
| qwen2.5-coder:14b | 5 | 3/5 | 3/5 | 1/5 | 1/5 | 0/5 | 0/5 | 400 | 1446997 |
| qwen2.5-coder:7b | 5 | 4/5 | 4/5 | 0/5 | 0/5 | 0/5 | 0/5 | 400 | 1164181 |

## 2. Five-agent Qwen 7B vs single-agent Qwen 7B

| System | Seeds | Executable | Routing | Charging | Multi-customer | Schneider C5 panel | All C5 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| five-agent Qwen 7B | 5 | 4/5 | 4/5 | 0/5 | 0/5 | 0/5 | 0/5 |
| single-agent Qwen 7B | 5 | 2/5 | 1/5 | 0/5 | 0/5 | 0/5 | 0/5 |

## 3. Qwen 7B vs Qwen 14B (five-agent)

| Model | Seeds | Schneider C5 panel | All C5 | LLM calls | Tokens |
| --- | --- | --- | --- | --- | --- |
| Qwen 7B | 5 | 0/5 | 0/5 | 400 | 1164181 |
| Qwen 14B | 5 | 0/5 | 0/5 | 400 | 1446997 |

## 4. Solver evolution

| Seed | Improved | All C5 | Vehicles | Distance | Calls | Hash | Runtime s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| — | — | — | — | — | — | — | — |

Valid improvements kept: 0.

Evolution did not start: no valid synthesized solver to evolve.

## 5. Failure categories

| Failure | Count |
| --- | --- |
| crash | 20 |
| 0 | 1 |
| 'D' | 1 |
| BATTERY | 1 |
| DEPOT | 1 |
| timeout | 1 |

## Best valid generated solver

No run produced a solver that is fully feasible on every non-held-out 5-customer instance.

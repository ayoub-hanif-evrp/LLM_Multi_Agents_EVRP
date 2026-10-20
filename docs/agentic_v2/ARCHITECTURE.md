# Agentic solver architecture

The primary method is five LLM agents constructing or repairing an EVRP solution. Classical ALNS in `src/evrptw_autolab/backbone/` remains a separate baseline. This package does not call it.

## Roles

1. **Architect** reads the instance summary and names the native objective and the capability flags that apply. Constraints that are not in the capability list are dropped.
2. **Routing** either returns explicit customer sequences (15 customers or fewer) or writes `solve(instance) -> dict` (more than 15 customers).
3. **Charging** inserts station stops with an amount and a technology when the family needs them.
4. **Optimization** may relocate at most four customers. A move is kept only when the independent evaluator reports a better feasible objective.
5. **Critic** reads the evaluator report and names the next owner. An invalid name is replaced by the fault map and that replacement is stored in the trace.

## Fault map

| Evaluator family | Next owner |
| --- | --- |
| VISIT, DEPOT, CAPACITY, WINDOW, PRECEDENCE, PAIRING, FLEET | routing |
| BATTERY, CHARGE_POLICY | charging |
| DURATION | optimization |
| anything else | architect, which ends the repair loop |

## Execution

`evaluate_solution_v2` runs in the parent process. Generated source is scanned, rejected if it mentions `solve_classical` or `evrptw_autolab.backbone`, and then run in a subprocess with a time limit. The subprocess returns JSON. The parent does not unpickle model output.

## Attribution

A saved run has `method: agentic_v2` and `classical_alns_used: false`. Mode `explicit_routes` means the model named the stops. Mode `generated_solver` means the model wrote the function that named the stops. Deterministic code only checks ids, inserts a requested station, relocates a requested customer, and evaluates.

## Commands

```powershell
uv run voltforge agentic solve --family schneider --instance c101C5 --model qwen3_coder_30b
uv run voltforge agentic benchmark --family schneider --model qwen3_coder_30b --resume --max-instances 1
```

`--max-instances` defaults to 1 so a benchmark command cannot start all 426 instances by accident. A full manifest needs a raised cap and a separate time estimate.

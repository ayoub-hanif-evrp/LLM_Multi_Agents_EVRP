# CIPHER-EVRP architecture

## What runs now

```text
benchmark file
    -> problem/datasets parser
    -> ProblemSpecV2
    -> ClassicalSolver (optional OperatorSpec)
    -> construction + ALNS + charging repair
    -> evaluate_solution_v2
```

`OperatorSpec` records required and forbidden `CapabilityFlags`. Hard compatibility rejects an incompatible operator before search. A restricted expression language scores screened insertion candidates. Selective applicability applies the operator only when the rule score is positive; otherwise the classical path is kept.

When `hard_timeout=True`, the child process reconstructs `OperatorSpec` from JSON (`discovery/policy_codec.py`). Attribution follows the executed child policy (`policy_executed`, `source_hash`, `changed_decisions`), not an unused parent object.

`experiment_partition` is plumbed into ALNS repair. Counterexample mining and applicability fitting refuse `confirmation` and `heldout`.

For Schneider/Goeke, simulated annealing rejects vehicle-worsening moves before scalar Metropolis. Context features use peak onboard load (signed PD demand cannot cancel utilization to zero).

## Optional live discovery

`discovery run --backend ollama --live` and `research live-signal --backend ollama --live` call a resolved Ollama model under a hard call/token/wall budget. Fake backend remains the CI default. Malformed proposals, capability rejection, and behaviorally inert operators stop the gate; call caps are not raised.

## What is not claimed

A live multi-agent campaign that improves the five benchmarks has not been completed. The scripted B0–B6 four-node comparison and the first live Qwen signal are development evidence only. Schneider RC2 is not a blind final test.

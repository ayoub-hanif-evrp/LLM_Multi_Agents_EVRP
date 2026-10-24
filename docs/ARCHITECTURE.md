# CIPHER-EVRP architecture

The hypothesis under test is that an operator can be stored with its physical compatibility conditions, and that measured failures can later decide where that operator is allowed to run. The hypothesis is not a result.

## What runs now

```text
benchmark file
    -> problem/datasets parser
    -> ProblemSpecV2
    -> backbone classical construction, ALNS, charging repair
    -> evaluate_solution_v2
```

`OperatorSpec` records required and forbidden `CapabilityFlags`. `compatibility_failures` rejects an operator before search. A restricted expression in `discovery/policy_language.py` can score candidate rows. `select_operator` applies that operator only when the capability check passes and the expression score is positive. Otherwise it keeps the classical fallback or abstains. `differential_counterexample` compares two solutions with `evaluate_solution_v2` and refuses confirmation and held-out partitions.

## What does not run yet

The selective controller is not inside the ALNS loop. Specialist agents, a learned applicability model fitted on development runs, counterexample search over benchmark panels, and the B0–B6 comparison are not in this branch. The LLM package remains available and is not on the solver path.

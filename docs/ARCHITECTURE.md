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

`repair_greedy` calls that controller when the caller passes an `OperatorSpec`. On one removed customer it screens feasible insertions, keeps the classical row when the rule is non-positive or the capability check fails, and otherwise ranks those rows with the restricted scoring expression. A worse applied row is stored as a counterexample. ALNS still publishes an incumbent only when `is_better` says so. Mining is refused on confirmation and held-out partitions.

Destroy, charging, and fleet operators use the same controller when their family matches. A one-feature stump can be fit on development labels. A scripted discovery cycle can revise an applicability rule after a counterexample, under a call budget. The default solver still passes no operator. The B0–B6 numbers in `docs/MANUSCRIPT.md` are that scripted four-node repair, not a live-model campaign.

# Counterexample records

`objective_counterexample` records two outcomes:

- the candidate loses feasibility while the baseline stays feasible
- both stay feasible and the candidate native objective is strictly worse

An improvement returns no record. `minimize_failing_case` drops elements from a small failing set while a caller-supplied predicate still fails.

`differential_counterexample` evaluates a baseline solution and a candidate solution with `evaluate_solution_v2`. `replay_matches` evaluates that same pair again. `refuse_non_development` rejects the confirmation and held-out partitions before evaluation.

These helpers do not search a benchmark panel and do not call a model. They compare solutions the caller already built.

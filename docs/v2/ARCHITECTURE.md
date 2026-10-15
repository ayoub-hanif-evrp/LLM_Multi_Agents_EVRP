# VoltForge 2.0 Architecture (living)

## Trust boundary

| Layer | Trust | Role |
|-------|-------|------|
| Dataset parsers | Trusted | Raw files → immutable `ProblemSpecV2` |
| `evaluate_solution_v2` | Trusted | Feasibility + objective; **never** calls LLM |
| Sandbox / `safe_exec` | Untrusted code host | Runs generated solvers in a subprocess |
| Agents / LLM backends | Untrusted advice | Propose code only |

An LLM opinion never overrides the evaluator.

## Module map (v2)

```
problem/v2/
  types.py           ProblemSpecV2, SolutionV2, CapabilityFlags
  transport.py       Distance / time / energy (Euclidean or matrix)
  charging.py        Full/partial linear, nonlinear piecewise, multi-tech
  route_simulator.py State propagation
  evaluator.py       Variant-aware oracle → EvaluationReportV2
  report.py          Diagnostics for Critic agents
problem/datasets/    Family parsers (Schneider adapter + 4 new families)
sandbox/safe_exec.py Shared subprocess boundary for generated code
backbone/            Classical construction, energy repair, local search, ALNS
                     (human-authored Track 2 scaffolding; no LLM calls)
```

## Classical baseline (Milestone 4)

`ClassicalSolver` / `solve_classical(spec, seed=..., time_limit_s=...)`:

1. Cheapest feasible insertion (TW/capacity; PD pair insertion for Goeke)
2. Battery repair via charging-station insertion
3. Relocate / 2-opt
4. ALNS (random/worst destroy + greedy repair + SA)
5. Redundant station removal

Feasibility is always decided by `evaluate_solution_v2`.

## Legacy

Experiment A/B Schneider evaluator (`problem/evaluator.py`) remains frozen for historical results.
`load_schneider_v2` adapts instances into the v2 representation without changing legacy scoring files.

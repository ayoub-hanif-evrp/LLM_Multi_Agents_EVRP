# Reference analysis for the five-agent EVRP solver

This note records what the cited agentic routing systems actually do, and what VoltForge does differently. It is not a claim that VoltForge matches their published numbers.

## What the frameworks implement

**AFL** (Zhang et al., arXiv:2510.16701, code `ZHANG-NI/AFL`) uses four roles: a generation agent, a judgment agent, a revision agent, and an error-analysis agent. The work is split into problem description, code generation, and solution derivation. Functions are written one at a time, reviewed, and repaired from execution errors. A buffer reuses earlier code. Their runner is `python main.py` followed by `python test.py`. The paper reports experiments on 60 complex VRPs and feasibility close to 100% against other LLM baselines, with performance described as comparable to designed algorithms. Those figures are AFL's reported results on AFL's instances. They were not re-run here and they are not VoltForge results.

**DRoC** (code `Summer142857/DRoC`) decomposes routing constraints, prompts a model to generate solver code that respects those constraints, and debugs that code from execution errors. The useful idea is that a failed run returns a concrete error to the same generator, rather than a free-form critique.

**ARS** (arXiv:2502.15359, code `Ahalikai/ARS-Routbench`) turns a problem description into a solving strategy and evaluates the generated solver on a benchmark. ARS uses a classical algorithmic backbone. That is a legitimate design for a generated solver. It is not evidence that an agent itself produced the routes when the backbone did the search.

**RLEA** (arXiv:2609.00859) adds reinforcement learning around LLM routing agents. VoltForge does not use reinforcement learning. The reusable part is the feedback loop: an agent proposes, an executor runs, and a later agent sees the measured outcome.

## What is reusable

- Separate the problem reading, the route construction, the repair, and the check.
- Execute generated code and return the execution error, not an LLM's opinion of the code.
- Keep a previous feasible result when a later attempt is worse.
- Bound the number of repairs.

## How their formulations differ from these five families

AFL, DRoC, and ARS are built around CVRP and VRPTW-style problems: customers, capacity, and time windows. The five families in this repository add physics those formulations do not share:

- Schneider: battery, charging stations, and a full recharge, with vehicle count then distance.
- Montoya: published nonlinear charging curves, partial charge, and a duration objective.
- Bezzi: technology-specific charging amounts and a recharge-cost objective.
- Goeke: pickup before delivery on the same vehicle.
- Hiermann: conventional, plug-in hybrid, and battery-electric vehicles, with a money objective.

A solver that is feasible on a CVRP instance is not a solution to these families. Averaging their objective values is not meaningful.

## What their results do and do not establish

Their papers establish that an LLM can generate and repair routing code on the benchmarks they chose, under the constraints they encoded. They do not establish that a five-agent system has solved the 426 instances in this repository. They do not establish that a classical ALNS run is an agent result. VoltForge's earlier 39/39 feasibility freeze is a classical backbone result and stays labeled that way.

## How VoltForge differs

VoltForge keeps five named roles (architect, routing, charging, optimization, critic) and one independent checker, `evaluate_solution_v2`. The critic may recommend acceptance. The evaluator decides. Charging decisions are explicit for families that require them. Generated code is executed on a JSON `ProblemSpecV2` and may not call `solve_classical`. If a later experiment uses ALNS, the record must say so. Mode A proposes routes for a small instance. Mode B writes a `solve(instance)` function for a larger instance. The two modes are stored separately.

## Why this can solve a real instance

The parsers already build a `ProblemSpecV2` for each family. The evaluator already checks coverage, depots, capacity, time windows, battery, charging policy, pickup-delivery precedence, fleet, duration, and the native objective. The new loop only adds a bounded way for the model to propose routes or a solver, and a bounded way to repair the first evaluator fault. A feasible output is a `SolutionV2` that this evaluator accepts. An infeasible output stays an infeasible output.

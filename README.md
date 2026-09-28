# VoltForge

**VoltForge** is a five-agent autonomous algorithm-development laboratory for the Electric Vehicle Routing Problem with Time Windows (EVRPTW). Five specialized LLM agents design, implement, test, and evolve a reusable solver. After synthesis, the solver executes with **zero LLM calls**.

The name is not AutoLab. [AutoLab (arXiv:2606.05080)](https://arxiv.org/abs/2606.05080) is a separate 2026 benchmark for long-horizon autonomous research agents. This project is VoltForge.

The paper claim is solver *synthesis*, not “best EVRPTW metaheuristic.” The generated solver must show real optimization (fleet/distance reduction), not only feasibility. The Python package remains `evrptw_autolab` for now; the user-facing name is VoltForge.

## Five agents, many models

The logical team is always the same five roles:

1. Solver Architect & Theorist
2. Routing Algorithm Engineer
3. Charging & Constraint Algorithm Engineer
4. Search Strategy & Integration Engineer
5. Adversarial Test & Evolution Critic

What varies in the main experiment is the **LLM model** that instantiates this five-agent team. Each compared model runs the full architecture with that same model assigned to all five roles, under identical prompts, solver-evaluation budgets, token/call limits, datasets, seeds, and stopping criteria.

The laboratory provides the EVRPTW specification, numerical APIs, sandbox, compiler/runtime errors, experiment runner, and evaluator. It does **not** supply construction, charging-repair, merge, acceptance, or a hidden fallback solution.

## Setup

```bash
uv sync
uv run pytest -q
uv run ruff check src/evrptw_autolab tests
uv run mypy src/evrptw_autolab
uv run voltforge validate-data
uv run voltforge models list
```

The frozen 92-instance contract is `docs/BENCHMARK_CONTRACT.md`.

Configured comparison models live in `configs/models.yaml`. A missing local model is recorded as `SKIPPED_NOT_INSTALLED`; it is never silently replaced.

## Package

`src/evrptw_autolab/` — problem contract, sandbox, five-agent orchestration, and homogeneous-team model comparison. Generated solvers live under `workspace/discovery/` and can be exported with `voltforge export`.

## Continue after switching PCs

Read **[`NEXT.md`](NEXT.md)** and `results/md/SLM_EVO_STATUS.md` (SLM-Evo state, OPT_V1/OPT_V2 freezes, next scale-aware experiment). Do not rely on chat history.

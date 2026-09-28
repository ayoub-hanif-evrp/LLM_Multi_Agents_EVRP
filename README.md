# VoltForge

Local coding models act as agents, write an EVRPTW solver, execute it, receive evaluator feedback, and improve the code. After synthesis or evolution, the solver runs with **zero LLM calls**.

The problem is Schneider’s Electric Vehicle Routing Problem with Time Windows (full recharge). The laboratory provides the instances, the physics API, a sandbox, and an exact evaluator. It does not provide a route-construction method or a hidden fallback solver.

## Experiments

| Name | What it does |
| --- | --- |
| `five_agent_synthesis` | Five roles (architect, routing, charging, search, critic) share one local model and create a solver from scratch. |
| `single_agent_synthesis` | One coding agent receives the same problem and API information and creates a solver alone. |
| `solver_evolution` | Starting from a valid generated solver, the model proposes small code patches. Only feasible improvements are kept. |
| `evaluation` | Run a frozen solver with no language model. |

```bash
uv sync
uv run pytest -q
uv run ruff check src tests
uv run voltforge validate-data
uv run voltforge models list

uv run python scripts/run_five_agent.py --all
uv run python scripts/run_single_agent.py --all
uv run python scripts/run_evolution.py --all
uv run python scripts/generate_paper_results.py
```

Models, seeds, and the shared call budget live in `configs/models.yaml` and `configs/experiments.yaml`. A missing local model is recorded as `SKIPPED_NOT_INSTALLED` and is not replaced.

Paper tables are written to `results/paper/`.

## Dataset

92 Schneider instances in `dataset/schneider/`. Discovery uses families C1 and R1. Confirmation uses C2, R2, and RC1. RC2 stays held out. See `docs/BENCHMARK_CONTRACT.md`.

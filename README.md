# VoltForge

Local coding models act as agents, write an EVRPTW solver, execute it, receive evaluator feedback, and improve the code. After synthesis or evolution, the solver runs with **zero LLM calls**.

```
LOCAL CODING MODELS
        ↓
5 SPECIALIZED AGENTS
        ↓
GENERATED solver.py
        ↓
DETERMINISTIC EVRPTW EVALUATOR
        ↓
FEEDBACK + REPAIR
        ↓
FROZEN SOLVER
        ↓
ZERO LLM CALLS AT DEPLOYMENT
```

The laboratory provides instances, the physics API, a sandbox, and an exact evaluator. It does not provide a route-construction method or a hidden fallback solver.

## Experiments

| Name | What it does |
| --- | --- |
| `five_agent_synthesis` | Architect, Routing, Charging, Search, Critic share one local model and create a solver. Each coding role returns a complete `solver.py` candidate. |
| `single_agent_synthesis` | One coding agent receives the same problem and API information and creates a solver alone. |
| `solver_evolution` | Starting from a valid generated solver, the model proposes small code patches. Only feasible improvements are kept. |
| `evaluation` | Run a frozen solver with no language model. |

```bash
uv sync
uv run pytest -q
uv run ruff check src tests
uv run mypy src/evrptw_autolab
uv run voltforge validate-data
uv run voltforge models list

uv run python scripts/smoke_micro.py
uv run python scripts/run_final_experiments.py
```

Models, seeds, and the shared call budget live in `configs/models.yaml` and `configs/experiments.yaml`. A missing local model is recorded as `SKIPPED_NOT_INSTALLED` and is not replaced.

Paper tables are written to `results/paper/`. Run provenance is copied to `results/paper/raw/`. Temporary `workspace/` is gitignored. Earlier engineering-validation artifacts remain in `results/engineering_validation/`.

## Dataset

92 Schneider instances in `dataset/schneider/`. Discovery uses families C1 and R1. Confirmation uses C2, R2, and RC1. RC2 stays held out. See `docs/BENCHMARK_CONTRACT.md`.

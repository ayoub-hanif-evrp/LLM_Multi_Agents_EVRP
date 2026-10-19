# Reproduce

From the repository root, with the local environment:

```
uv run pytest -q
uv run ruff check src tests
uv run mypy src
uv run voltforge validate-data
uv run voltforge research-ready --checks-only
uv run python scripts/freeze_classical.py
uv run python scripts/profile_large_dev.py
uv run python src/evrptw_autolab/experiments/generational_compare.py --fake --micro --candidates 2
uv run python src/evrptw_autolab/experiments/generational_compare.py --seed 7 --candidates 4
uv run python scripts/confirm_after_selection.py
uv run python scripts/build_paper_package.py
```

The live command needs local Ollama and `qwen3-coder:30b`.
The fake command is a plumbing check. Do not cite it as model evidence.
Do not overwrite `results/v2/baselines/classical/run_27278a1_seed7_20261018T203033Z` or the historical campaign directories.

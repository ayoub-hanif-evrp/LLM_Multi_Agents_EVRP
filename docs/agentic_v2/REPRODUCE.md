# Reproduce the agentic solver

## Plumbing tests

```powershell
uv run pytest tests/test_agentic_v2.py -q
uv run ruff check src/evrptw_autolab/agentic_v2 tests/test_agentic_v2.py
uv run mypy src/evrptw_autolab/agentic_v2 src/evrptw_autolab/components/expressions.py
```

These tests use `FakeBackend`. They do not contact Ollama. A passing test means the five roles, the evaluator, and the generated-code subprocess are wired. It does not mean a live model solved an instance.

## One live instance

Ollama must already be serving `qwen3-coder:30b`.

```powershell
uv run voltforge agentic solve --family schneider --instance c101C5 --model qwen3_coder_30b
```

The same command works with `--family montoya --instance tc0c10s2cf1`, `--family bezzi --instance C101-5`, `--family goeke --instance c101C6`, and `--family hiermann --instance c101_21`.

Each run writes `results/agentic_v2/runs/<family>_<instance>.json` with the source sha256, the agent trace, the routes, the evaluator report, the call count, and the status.

## A dataset slice

```powershell
uv run voltforge agentic benchmark --all-families --model qwen3_coder_30b --resume --max-instances 1
```

`--resume` skips a family/instance file that already exists. The default cap is one new instance per family. Raising it toward 426 is a multi-hour run and should be estimated before it is started.

Historical files under `results/paper/`, `results/structured/`, and `results/v2/` are a different method and are not inputs to this command.

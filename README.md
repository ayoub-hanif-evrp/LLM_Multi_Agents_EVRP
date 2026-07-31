# ChargeCEGIS

Counterexample-guided small-LLM discovery of coupled route-and-charging policies for EVRPTW.

## Architecture

```
Schneider instances → construction / ALNS
                         ↑
five LLM roles → typed JSON policy DSL → ranks fixed coupled moves
```

Exactly five roles: Analyst, Scientist, Synthesizer, Counterexample Agent, Critic.

The LLM never builds routes or executes moves. It only emits a compact priority policy AST.

## Setup

```bash
uv sync
uv run pytest -q
uv run ruff check src/chargecegis tests
uv run mypy src/chargecegis
```

Primary model config: `configs/models.yaml` (`qwen2.5-coder:3b`).

## Package

`src/chargecegis/` — focused research package (~15–17 modules).

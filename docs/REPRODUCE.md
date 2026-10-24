# Reproduce

```text
uv sync
uv run pytest -q
uv run ruff check src tests
uv run mypy src/evrptw_autolab
uv run voltforge datasets validate
```

A short classical solve:

```text
uv run voltforge solver run --family schneider --instance c101C5 --time-limit 5 --iterations 20
```

The archived VoltForge tree is `archive/pre-cipher-61cdc20` at `61cdc20625061c4a11f31c0f9ddbe6f9bb6d3a78`.

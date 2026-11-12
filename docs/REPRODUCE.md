# Reproduce

```text
uv sync
uv run pytest -q
uv run ruff check src tests
uv run mypy src/evrptw_autolab
uv run voltforge datasets validate
```

Classical smoke:

```text
uv run voltforge solver run --family schneider --instance c101C5 --partition development --time-limit 5 --iterations 20
uv run voltforge solver run --family hiermann --instance c101_21 --partition development --time-limit 8 --iterations 10
```

CIPHER research path:

```text
uv run voltforge research freeze-classical
uv run voltforge research live-signal
uv run voltforge research report
```

Live Ollama (optional, local model required):

```text
uv run voltforge discovery run --backend ollama --live --model-id qwen25_coder_14b --max-calls 4
uv run voltforge research live-signal --backend ollama --live --model-id qwen25_coder_14b
```

Archive tags for historical trees: `archive/pre-cipher-61cdc20`, `archive/main-unrelated-history`.

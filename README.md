# CIPHER-EVRP

Counterexample-guided, physics-aware transfer of search operators across electric-vehicle routing families.

The active system is a trusted evaluator (`evaluate_solution_v2`), a classical ALNS backbone, and typed `OperatorSpec` discovery/transfer contracts. Live LLM discovery is optional, budget-capped, and fail-closed. Generated agents are not on the default solve path.

Historical VoltForge agent stacks and the unrelated `main` history are preserved as Git tags:

- `archive/pre-cipher-61cdc20`
- `archive/main-unrelated-history`

## Commands

```text
uv sync
uv run voltforge datasets validate
uv run voltforge solver run --family schneider --instance c101C5 --partition development --time-limit 5 --iterations 20
uv run voltforge policies validate --policy operator.json --family schneider
uv run voltforge counterexamples generate
uv run voltforge discovery run
uv run voltforge discovery run --backend ollama --live --model-id qwen25_coder_14b
uv run voltforge transfer evaluate
uv run voltforge research freeze-classical
uv run voltforge research live-signal
uv run voltforge research live-signal --backend ollama --live
uv run voltforge research report
```

`--partition` is required for solver runs (`development|discovery|confirmation|heldout`). Counterexample mining and applicability fitting refuse confirmation/held-out partitions.

## Tests

```text
uv run pytest -q
uv run ruff check src tests
uv run mypy src/evrptw_autolab
```

## Documentation

- `docs/ARCHITECTURE.md` — current system
- `docs/BENCHMARK_CONTRACT.md` — Schneider primary contract
- `docs/MATHEMATICAL_CONTRACTS.md` — five-family objective/physics pointers
- `docs/v2/VARIANT_CONTRACTS.md` — family capability contracts
- `docs/EXPERIMENTAL_PROTOCOL.md` — development vs confirmation rules
- `docs/REPRODUCE.md` — reproduction checklist

## Status

Policy spawn through hard timeout, partition fail-closed mining, lexicographic SA for fleet-first families, and peak-load context features are in place. A classical Schneider+Hiermann panel is frozen under `results/cipher/classical/`. The first live Qwen signal is recorded under `results/cipher/live_signal/ollama_signal.json` as an honest `behaviorally_inert` gate. Schneider RC2 is not a blind final test.

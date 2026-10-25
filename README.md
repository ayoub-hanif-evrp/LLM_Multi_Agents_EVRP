# CIPHER-EVRP

Counterexample-guided transfer of search operators across electric-vehicle routing families. The classical optimizer and the trusted evaluator are the active system. Generated agents are not on the solve path.

The previous VoltForge agent, synthesis, and expression-policy stacks are archived at `archive/pre-cipher-61cdc20` (`61cdc20625061c4a11f31c0f9ddbe6f9bb6d3a78`). See `docs/MIGRATION.md`.

## Commands

```text
uv run voltforge datasets validate
uv run voltforge solver run --family schneider --instance c101C5 --time-limit 5 --iterations 20
uv run voltforge policies validate --policy operator.json --family schneider
uv run voltforge counterexamples generate
uv run voltforge discovery run
uv run voltforge transfer evaluate
uv run voltforge research report
```

`datasets validate` checks that the Schneider, Montoya, Bezzi, Goeke, and Hiermann files still parse. `solver run` uses the classical engine and prints the native objective from `evaluate_solution_v2`. A model is not called.

## Tests

```text
uv run pytest -q
uv run ruff check src tests
uv run mypy src/evrptw_autolab
```

## Status

Selective repair, destroy, charging, and fleet decisions exist. A development stump can abstain where an operator failed. One scripted discovery cycle revises that rule after a measured regression. The B0–B6 report on the four-node repair uses no live model: the always-applied harmful arm is worse, and the selective arms tie the classical objective. That is one repair, not a significant result. Schneider RC2 is not a blind final test. No claim is made that a generated operator improves the five benchmarks.

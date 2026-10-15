# Classical baseline pilot (no LLM)

Human-authored Track-2 solver only (`backbone`). LLM calls = 0.

## Reproduce

```powershell
uv run voltforge baselines pilot --seed 7
```

## Latest aggregate (seed 7)

See `summary.json` / `latest.json` for the authoritative numbers. As of the pilot that wrote those files:

| Family | Instances | Feasible | Rate | Notes |
|---|---:|---:|---:|---|
| Schneider | 5 | 4 | 0.80 | C5 development panel |
| Montoya | 2 | 0 | 0.00 | Battery/duration after construction; nonlinear partial-charge repair still weak |
| Bezzi | 3 | 2 | 0.67 | Charge plans completed by optimizer DP, not the evaluator |
| Goeke | 3 | 2 | 0.67 | One WINDOW failure on `rc105C6` |
| Hiermann | 1 | 1 | 1.00 | `c101_21`, mostly ICEV assignment, cost ~4207.6 |

These are measured classical results, not multi-agent discoveries.

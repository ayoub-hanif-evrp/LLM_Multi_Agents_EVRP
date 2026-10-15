# Classical baseline pilot (no LLM)

Human-authored Track-2 solver only (`backbone`). LLM calls = 0.

## Reproduce

```powershell
uv run voltforge baselines pilot --seed 7
```

Results are written under `run_<git_commit>_seed<seed>_<utc>/` and mirrored to `latest.json` / `summary.json`.

## Result provenance

| Artifact | Originating commit | Seed | Feasible | Notes |
|---|---|---:|---:|---|
| `checkpoint_6925de8_seed7.json` | `6925de8e5444` | 7 | **9/14** | Frozen pre-repair pilot (do not overwrite) |
| `run_6925de8_seed7_20261015T202644Z/` | working tree on `6925de8` (pre-push repair) | 7 | 12/14 | Intermediate repair checkpoint |
| `run_6925de8_seed7_20261015T203302Z/` | working tree on `6925de8` (pre-push repair) | 7 | **14/14** | First full-panel feasible pilot |
| `latest.json` / `summary.json` | commit that last ran the pilot (see `git_commit` field inside) | 7 | **14/14** | Convenience mirrors of the newest run |

The **14/14** claim refers to one development seed on the fixed 14-instance panel. It is **not** a multi-seed or held-out result.

## Latest aggregate (seed 7, 14/14 run)

Authoritative numbers: `latest.json` / `summary.json` and
`run_6925de8_seed7_20261015T203302Z/`.

| Family | Instances | Feasible | Rate | Notes |
|---|---:|---:|---:|---|
| Schneider | 5 | 5 | 1.00 | C5 development panel; lex vehicles then distance |
| Montoya | 2 | 2 | 1.00 | Feasible via multi-stop charge + splits; duration ~31.3 (not competitive) |
| Bezzi | 3 | 3 | 1.00 | Charge plans by optimizer DP; evaluator verifies only |
| Goeke | 3 | 3 | 1.00 | PD pair moves + TW-safe charging |
| Hiermann | 1 | 1 | 1.00 | `c101_21`, cost ~4211.7, mostly non-charging fleet |

These are measured classical results, not multi-agent discoveries.
Compare against `checkpoint_6925de8_seed7.json` (9/14) when claiming regressions or improvements.

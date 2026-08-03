# ChargeCEGIS results

## Status warning

Previous unequal-budget comparison outputs live in `results/invalid_previous/` and are marked:

**INVALID_FOR_METHOD_COMPARISON**

Do not cite `results/invalid_previous/` for method comparison.

## Frozen pilot (do not treat as paper evidence)

The completed two-iteration full-dataset campaign under this tree is labeled:

**PRELIMINARY_TWO_ITERATION_PILOT**

Source hash at freeze: see `results/manifests/source_hash.json`.

These results are a preliminary ranking pilot only. They are not final paper evidence.

Known limitations of that pilot (addressed in the next repair):
- large pools were singleton-heavy;
- counterexamples did not fully exercise the `RemovalUnit → top-k → repair` path;
- tie-breaking could depend on entity identities;
- statistics used independent per-metric medians before pairing;
- only two ALNS iterations.

## Active experiment status values

```text
PRELIMINARY_TWO_ITERATION_PILOT
BUDGET_SENSITIVITY_PILOT
SMALL_LLM_GP_PILOT
FINAL_PAPER
```

Nothing in this repair phase is marked `FINAL_PAPER`.

## Equal-budget contract

Equal-budget ranking methods share:
- the same merged initial solution (per instance/seed);
- the same stratified candidate pool and hash;
- the same selected-unit count `k` (non-overlapping);
- the same charging-aware repair;
- the same lexicographic acceptance;
- the same iteration budget and RNG stream definitions.

Only the ranking score may differ.

`CLASSIC_ALNS_REFERENCE` is reported separately and is never placed in equal-budget win/tie/loss tables.

## Commands

```bash
python -m chargecegis.experiment validate-core
python -m chargecegis.experiment validate-results
python -m chargecegis.experiment run-budget-pilot
python -m chargecegis.experiment run-discovery-smoke
python -m chargecegis.experiment run-small-llm-gp-pilot
python -m chargecegis.statistics
python -m chargecegis.plots
```

## Layout

```text
results/
├── raw/
│   ├── runs/
│   ├── invocations/
│   ├── solutions/
│   ├── full_dataset_runs.csv
│   ├── move_invocations.csv
│   └── paired_seed_results.csv
├── tables/
├── figures/
├── manifests/
├── invalid_previous/
└── README.md
```

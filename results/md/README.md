# VoltForge results

Date: 1 September 2026  
Experiment: homogeneous **five-agent** teams × local LLM models on Schneider EVRPTW (full recharge).  
Partitions: **C1+R1 discovery**, **C2+R2+RC1 confirmation**, **RC2 held out**.

**Start here:** [DISCOVERY.md](DISCOVERY.md) (clean-autonomy `discovery_v2`). Historical prototype write-up: [REPORT.md](REPORT.md). Contract: `docs/BENCHMARK_CONTRACT.md`.

## Contents

| File | What it is |
| --- | --- |
| [DISCOVERY.md](DISCOVERY.md) | Clean five-agent × model campaign (15 cycles) |
| [REPORT.md](REPORT.md) | Full write-up plus historical Spark/prototype runs |
| [figures/](figures/) | PNG plots |
| [tables/](tables/) | CSV/JSON tables |
| [solvers/discovery_v2/](solvers/discovery_v2/) | Elite generated solvers |

## Discovery_v2 figures and tables

| File | What it is |
| --- | --- |
| [voltforge_discovery_f1.png](figures/voltforge_discovery_f1.png) | F1 feasible rate (all zero) |
| [voltforge_discovery.csv](tables/voltforge_discovery.csv) | Main model table |
| [voltforge_discovery_summary.csv](tables/voltforge_discovery_summary.csv) | Faults, RETAIN counts |
| [voltforge_quality_small_all.csv](tables/voltforge_quality_small_all.csv) | 36 small × compile-valid models |
| [literature_small_cplex.csv](tables/literature_small_cplex.csv) | Schneider 2014 Table 3 (36 small) |

## Headline numbers (`discovery_v2`)

- Dataset: **92** Schneider instances (33 discovery, 45 confirmation, **14 RC2 held out**). Small: 12 + 18 + 6 = 36.
- Configured models: 5. Installed: **4**. `phi4-mini:3.8b` = `SKIPPED_NOT_INSTALLED` (not substituted).
- Compile-valid elites: 7B, 1.5B, Llama. 3B failed F0 (syntax).
- F1 feasible rate: **0.0** for every installed model.
- 36-small feasible: **0**. Large 56: not run.
- Only 1.5B moved the elite (`S010`); first-fault still **DEPOT**.
- Wall: **3435 s**. Ollama **0.32.3**.

# Mathematical contracts

Family physics and native objectives are defined here:

- `docs/BENCHMARK_CONTRACT.md` — Schneider primary laboratory contract
- `docs/v2/VARIANT_CONTRACTS.md` — Schneider, Montoya, Bezzi, Goeke, Hiermann
- `docs/v2/MATHEMATICAL_VALIDATION_REPORT.md` — validation notes for the five families
- `data/contracts/schneider_v1.0.json` — frozen Schneider dataset contract hash

The executable contract is `evaluate_solution_v2` with the parsers under `src/evrptw_autolab/problem/datasets/`. CIPHER-EVRP does not replace family objectives with one shared scalar.

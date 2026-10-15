# Structured synthesis results (Experiment B)

Predeclared experiment: **STRUCTURED SOLVER SYNTHESIS**.  
Does **not** replace Experiment A (`results/paper/`, tag `final-protocol-v1`).

Protocol tip: `structured-protocol-v1` (see `STRUCTURED_PROTOCOL_COMMIT.txt`).

## Layout

- `runs.csv` — one row per completed or skipped run
- `raw/<profile>_seed<seed>/` — result.json, rounds, llm_calls, solver.py, spec.json
- `solvers/<profile>_seed<seed>/solver.py` — published zero-LLM solvers
- `<profile>_seed<seed>.json` — stamped run report
- `pilot_console.log` — console tee from the 3-seed pilot

Skipped credential/model profiles write `SKIPPED_NO_CREDENTIAL` and never substitute another model.

**Do not** write Experiment A paper/campaign artifacts here. This tree never writes to `results/paper/`.

## Pilot (seeds 11, 22, 33) — frozen

| model | seed | deepest gate | best G4 | 4/4 | confirmation | calls | tokens | wall_s | solver hash | note |
|-------|------|--------------|---------|-----|--------------|-------|--------|--------|-------------|------|
| qwen3-coder:30b | 11 | (none) | 0/4 | no | — | 339 | 1 956 211 | 2805.4 | `5b861b0912af5986` | TypeError: `energy_required` missing `vehicle` |
| qwen3-coder:30b | 22 | (none) | 0/4 | no | — | 244 | 1 200 493 | 1792.4 | `fac3992475f8e582` | TypeError: `travel_time` missing `vehicle` |
| qwen3-coder:30b | 33 | multi_customer | **1/4** | no | — | 237 | 1 398 208 | 2295.3 | `68d2b455d86e1c2c` | G4 1/4; timeout |
| deepseek-v4-pro | 11–33 | — | — | — | — | 0 | 0 | — | — | `SKIPPED_NO_CREDENTIAL` |
| gpt-6-sol / Claude / Qwen480B | — | — | — | — | — | — | — | — | — | no API credentials in env |

### Verdict

- **Best model:** `qwen3-coder:30b` (only runnable profile in this pilot)
- **Best seed:** 33 — deepest gate `multi_customer`, **G4 1/4**, solver `68d2b455d86e1c2c`
- **4/4 achieved:** no → no freeze-for-confirmation, no held-out RC2/C10/C15, no optimization evolution
- **Cost:** local Ollama only (no billed API); total Qwen tokens ≈ 4.55M across three seeds
- **Next step:** supply `DEEPSEEK_API_KEY` (and optional frontier keys) and re-run the same predeclared pilot/campaign protocol without changing budgets or evaluator

Experiment B uses more algorithm-engineering scaffold than Experiment A (modular construct/repair/improve/solve, population archive, failure memory). That difference is intentional and must be stated in the paper.

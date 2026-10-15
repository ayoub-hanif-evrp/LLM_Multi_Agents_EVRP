# Structured synthesis results (Experiment B)

Outputs for `structured_synthesis` pilots and campaigns.

## Layout

- `runs.csv` — one row per completed or skipped run
- `raw/<profile>_seed<seed>/` — result.json, rounds, llm_calls, solver.py
- `solvers/<profile>_seed<seed>/solver.py` — published zero-LLM solvers
- `<profile>_seed<seed>.json` — stamped run report

Skipped credential/model profiles write `SKIPPED_NO_CREDENTIAL` (or Ollama skip
codes) into the JSON report and never substitute another model.

**Do not** write Experiment A paper/campaign artifacts here. This tree never
writes to `results/paper/`.

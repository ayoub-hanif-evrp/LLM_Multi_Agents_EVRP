# CIPHER solver hot-path performance report

Branch: `perf/cipher-solver-throughput`  
Harness: `scripts/profile_solver_hotpaths.py`  
Artifact: `results/cipher/diagnostics/perf_hotpaths.json`

## Changes delivered

1. **Cached `ProblemSpecV2.node_map`** — built once in `__post_init__` (frozen/slots-safe).
2. **Cheaper `clone_solution`** — copy route lists; share immutable `RouteStopV2` objects.
3. **Route-local ALNS repair screening** — capacity/windows via `screen_repair_route`; temporary battery debt still allowed; full `evaluate_solution_v2` retained for acceptance/publication.
4. **Bezzi charge-plan cache** — identical cleared route signatures reuse DP results.
5. **LLM discovery latency knobs** — Qwen 14B defaults `num_ctx=4096`, `num_predict=512`, `timeout_s=120`; CallBudget accounts for all `pending_usages` and clamps backend timeout to remaining wall time.
6. **Profiler harness** — in-process `cProfile` + counters (clones, full evals, screens, charge DP).

## After measurements (in-process, seed 7, hard_timeout=False)

| Family | Instance | Runtime (s) | Feasible | ALNS iters done |
|--------|----------|-------------|----------|-----------------|
| Schneider | c101C5 | 0.43 | yes | (see JSON) |
| Schneider | c101_21 | 10.01 | yes | |
| Hiermann | c101_21 | 1.68 | yes | |
| Montoya | tc0c10s2cf1 | 0.61 | yes | |
| Bezzi | C101-5 | 0.32 | yes | |
| Goeke | c101C6 | 0.21 | yes | |

Coarse CI signal on this workstation: full `pytest -q` dropped from ~88s (pre-hotpath) to ~37s after these changes, with **174 passed**.

## Correctness gates

- `uv run pytest -q` — 174 passed
- `uv run ruff check src tests` — clean
- `uv run mypy src/evrptw_autolab` — clean
- `uv run voltforge datasets validate` — five families OK

## Not claimed yet

- Matched before/after cProfile on the identical harness before the edits (edits landed first).
- A new live Ollama beneficial-operator experiment.
- Equal-wall-time quality ablations for polishing frequency.

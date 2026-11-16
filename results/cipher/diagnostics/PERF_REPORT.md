# CIPHER solver hot-path performance report

Branch: `master` only (redundant `perf/cipher-solver-throughput` deleted; both pointed at the same SHA).  
Harnesses: `scripts/profile_solver_hotpaths.py`, `scripts/compare_perf_baseline.py`, `scripts/verify_worker_equivalence.py`  
Artifacts: `perf_hotpaths.json`, `perf_before_after.json`, `spawn_overhead.json`, `worker_equivalence.json`

## Matched before/after (seeds 7, 11, 22; hard_timeout=False)

Baseline commit: `e6d94cfd5b0766f833a73caf6ee680ecf2ffdd8d`  
Current: HEAD at measurement time on `master`

| Instance | Baseline median (s) | Current median (s) | Speedup | Feasible (base/cur) | Same objective keys |
|----------|---------------------:|-------------------:|--------:|---------------------:|---------------------|
| Schneider `c101C5` | 0.115 | 0.077 | 1.49× | 3/3 | no |
| Schneider `c101_21` | 10.024 | 3.161 | 3.17× | 3/3 | no |
| Hiermann `c101_21` | 5.519 | 0.941 | 5.87× | 3/3 | no |
| Montoya `tc0c10s2cf1` | 1.633 | 0.435 | 3.76× | 3/3 | no |
| Bezzi `C101-5` | 0.962 | 0.171 | 5.62× | 3/3 | yes |
| Goeke `c101C6` | 0.284 | 0.094 | 3.04× | 3/3 | yes |

Interpretation: median wall-clock speedups are real under matched seeds/budgets/iteration caps. Where objective keys differ, the optimized search explores a different trajectory (more effective work per second / different candidate ordering after route-local screening). This is **not** a claim that every seed reproduces the identical classical incumbent.

## Profiler fix

`_top_functions()` now reads the cProfile ranking via sorted `fcn_list` / cumtime order instead of slicing the unsorted `stats` dict.

## Warm-worker equivalence

`worker_equivalence.json`: cold vs warm vs post-timeout/crash recovery agree on objective key, route fingerprint, changed decisions, attribution, and timeout flags for Schneider (classical + handcrafted policy) and Hiermann. In-process may still differ from spawn because spawn applies parent deadline margins.

Example `c101C5` (2s / 8 iters): in-process 0.12s, cold 0.96s, warm 0.11s.

## Proposal cache provenance

Cache version `2026-11-16.v2`. Keys include model name, **model digest**, role, temperature, seed, `num_ctx`, `num_predict`, schema digest, and prompt hash. Failed/repaired backend attempts still charge tokens via `_absorb_usages`. Opt-in only (`CIPHER_PROPOSAL_CACHE`).

## Correctness gates (this workstation)

- `uv run pytest -q` — 178 passed
- `uv run ruff check` — clean on edited paths
- `uv run mypy src/evrptw_autolab` — clean
- `uv run voltforge datasets validate` — five families OK

## Not claimed

- Publication-ready LLM operator transfer
- Blind final-test results (Schneider RC2 remains inspected / not blind)
- Averaged native objectives across EVRP families

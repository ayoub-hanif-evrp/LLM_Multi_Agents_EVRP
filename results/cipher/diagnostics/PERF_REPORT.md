# CIPHER solver hot-path performance report

Branch: `perf/cipher-solver-throughput`  
Harness: `scripts/profile_solver_hotpaths.py`  
Artifacts: `results/cipher/diagnostics/perf_hotpaths.json`, `spawn_overhead.json`

## Changes delivered

1. **Cached `ProblemSpecV2.node_map`** — built once in `__post_init__` (frozen/slots-safe).
2. **Cheaper `clone_solution`** — copy route lists; share immutable `RouteStopV2` objects.
3. **Route-local ALNS repair screening** — capacity/windows via `screen_repair_route`; temporary battery debt still allowed; full `evaluate_solution_v2` retained for acceptance/publication. Covers ordinary, selective, v4, and pair repair paths.
4. **Local-search screening** — relocate / relocate-pairs / 2-opt screen route-locally; 2-opt also skips non-shortening geometric moves.
5. **Bezzi charge-plan cache** — identical cleared route signatures reuse DP results.
6. **Warm hard-timeout worker** — reused spawn child across solves; killed and respawned on timeout/crash (measured ~0.60s saving on warm `c101C5` vs cold spawn).
7. **LLM discovery latency knobs** — Qwen 14B defaults `num_ctx=4096`, `num_predict=512`, `timeout_s=120`; CallBudget accounts for all `pending_usages` and clamps backend timeout to remaining wall time.
8. **Versioned proposal cache** — opt-in via `CIPHER_PROPOSAL_CACHE` (path or `1`); keyed by cache version, schema digest, model, role, prompt hash. Cache hits skip the backend and do not consume call budget.
9. **Profiler harness** — in-process `cProfile` + counters (clones, full evals, screens, charge DP) plus spawn cold/warm measure.

## After measurements (in-process, seed 7, hard_timeout=False)

| Family | Instance | Runtime (s) | Feasible |
|--------|----------|-------------|----------|
| Schneider | c101C5 | 0.26 | yes |
| Schneider | c101_21 | 8.16 | yes |
| Hiermann | c101_21 | 2.41 | yes |
| Montoya | tc0c10s2cf1 | 1.15 | yes |
| Bezzi | C101-5 | 0.60 | yes |
| Goeke | c101C6 | 0.32 | yes |

### Spawn overhead (`c101C5`, 2s budget)

| Mode | Runtime (s) |
|------|-------------|
| In-process | 0.28 |
| Hard-timeout cold | 0.85 |
| Hard-timeout warm | 0.09 |

Coarse CI signal on this workstation: full `pytest -q` ~38s with **176 passed**.

## Correctness gates

- `uv run pytest -q` — 176 passed
- `uv run ruff check` on edited paths — clean
- `uv run mypy src/evrptw_autolab` — clean
- EVRP math / battery-debt ALNS contract / trusted evaluator unchanged

## Not claimed

- A new live Ollama beneficial-operator experiment.
- Equal-wall-time quality ablations for polishing frequency.
- Matched before/after cProfile against the pre-hotpath commit (edits landed first; table above is post-change).

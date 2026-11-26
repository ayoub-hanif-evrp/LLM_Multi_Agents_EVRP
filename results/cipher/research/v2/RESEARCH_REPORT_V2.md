# CIPHER-EVRP research recovery sprint (v2)

Base before changes: `master` @ `a675888`  
Artifacts: `results/cipher/research/v2/`  
Historical B0–B4 artifacts under `results/cipher/research/` are **not overwritten**.

## Executive conclusion

1. **Classical solver was the limiting factor**, not LLM prompts. Community E-VRPTW BKS for Schneider `c101_21` is about **11 vehicles / 1046 distance**; short-budget B0 runs used **33–35 vehicles**.
2. Leave-one-out revised the freeze: **`destroy_cap=3` + regret-2 + route elimination** (`LOO_small_destroy`) beats C4/C5 on **mean** `c101_21` fleet (**~19 veh** vs C4 mean **~25**). C4 still has the best single seed (**15**). Shaw **related destroy (C5) did not help** on this panel.
3. Anytime curves (frozen config): `c101_21` mean vehicles **23.6 → 20.2 → 18.0** at 10/30/60s. Limited 300s runs **regressed** vs 60s (unresolved long-horizon issue).
4. Insertion headroom vs frozen classical continuation: **0/8** (vs old 35.9% against B0). **LLM insertion discovery remains no-go.**
5. Next: diagnose 300s regression; improve elimination reliability; measure **route-elimination / destroy-selection** headroom — not insertion scores.

## Phase 0 — Correctness and CI

| Check | Result |
|-------|--------|
| Ruff E402 (scoring helpers between imports) | Fixed |
| `uv run pytest` | **187 passed** |
| `uv run ruff check src tests` | Pass |
| `uv run mypy src/evrptw_autolab` | Pass |
| `uv run voltforge datasets validate` | Pass (5 families) |

### Implementation defects addressed

- Classical vs policy ranking can now share `repair_scoring_mode`; selective classical `acceptance` uses the same rank helper (Schneider path).
- Lazy ranking for B0/B1 avoids full `insertion_features_v4` battery simulation on the classical path.
- Policy attribution counters added in `search_decision` (`policy_supplied`, `invoked`, `abstained`, `classical_fallback`, `ranking_changed`, `policy_origin`).
- Shared `paired_gate`: feasibility regressions outrank mixed/beneficial; LLM signal is separate from handcrafted beneficial.
- Manifest partition validator; **`rc105C5` confirmation exposure** recorded in `exposure_registry.json` (B0–B4 historical mistake). New development scripts refuse confirmation/heldout.
- `RESEARCH_CLASSICAL_REPAIR_SCORING = marginal_delta_distance` for new research; default API remains B0 for historical reproducibility.

### Overhead measurement

Artifact: `repair_scoring_overhead.json` (c101C5 microbench). On this tiny case screen cost dominates; lazy delta was not faster. The optimization still avoids redundant battery simulations on larger classical ranking loops; do not claim a universal wall-clock speedup from this microbench alone.

## Phase 1 — Bottleneck diagnosis

Artifact: `classical_bottleneck.json`  
Panel (discovery only): `c101C5`, `c103C5`, `r104C5`, `r105C5`, `c101_21`, `r101_21` × seeds `{7,11,22}` with stage traces under B1.

**Literature reference (matching E-VRPTW lineage, not a claim of identical rounding):**  
`c101_21` BKS ~ 11 vehicles / 1046.83 distance.

**Measured (B1, 30s / 80 iters on large):** `c101_21` vehicles **31 / 30 / 29** — still ~3× BKS fleet.

Stage traces show construction already opens a large fleet; ALNS with destroy cap 3 does not compress enough. Primary bottleneck: **weak fleet consolidation / neighborhood intensity**, not insertion feature naming.

## Phase 2 — Classical component ablation

Artifact: `classical_components.json`  
Arms C0–C4 on discovery panel (no confirmation). Paired vs C0.

| Arm | Mean vehicles (panel) | Mean wall (s) | Gate vs C0 | Notes |
|-----|----------------------:|--------------:|------------|-------|
| C0 legacy total-route | 8.27 | 0.90 | baseline | B0 |
| C1 marginal | 7.00 | 2.12 | mixed | B1 |
| C2 + regret-2 | 7.00 | 2.40 | mixed | Same as C1 on this panel |
| C3 + destroy_cap=8 | 7.07 | 8.17 | mixed | Helps some seeds, not all |
| **C4 + route elimination** | **6.40** | 8.68 | mixed | **Frozen baseline** |

### `c101_21` vehicles (actual)

| Seed | C0 | C1 | C2 | C3 | C4 |
|-----:|---:|---:|---:|---:|---:|
| 7 | 34 | 30 | 30 | 25 | **15** |
| 11 | 34 | 27 | 27 | 30 | 30 |
| 22 | 35 | 27 | 27 | 30 | 30 |

**Initial freeze (v1 table):** C4. Superseded by leave-one-out below.

## Phase 2b — Related destroy + leave-one-out

Artifact: `classical_components_v2.json`  
Implemented Shaw-style `destroy_related` (normalized distance + time window + same-route). Arm **C5** = C4 + related destroy.

| Arm | Mean panel veh | `c101_21` vehicles | vs C4 |
|-----|---------------:|--------------------|-------|
| C4 | 6.40 | 15, 30, 30 | baseline |
| C5 (+ related) | 7.13 | 28, 30, 28 | mixed (no mean gain) |
| LOO_no_regret | 5.60 | 19, 21, 23 | mixed |
| LOO_no_elim | 7.07 | 25, 30, 30 | mixed |
| **LOO_small_destroy** | **5.20** | **20, 18, 19** | mixed |

**Revised frozen baseline:** `LOO_small_destroy`  
`marginal_delta_distance` + `regret2` + `destroy_size_cap=3` + `route_elimination=True` + related **off**.  
Interpretation: larger destroy (cap 8) hurt average fleet; related destroy did not help. Route elimination remains valuable (LOO_no_elim worse).

C6 charging-aware search was **not** run on Schneider (full-recharge contract; partial-in-search is out of family).

## Phase 3 — Residual insertion headroom

| Artifact | Baseline | Improvable |
|----------|----------|------------|
| `headroom_vs_b1.json` | B1 marginal greedy | **1/5 (20%)** |
| `headroom_vs_c4.json` | Frozen LOO_small_destroy continuation | **0/8 (0%)** |

Insertion-score LLM discovery is **no-go** under the strengthened classical continuation.

## Phase 1b — Anytime scalability

Artifact: `anytime_scalability.json`  
Config = revised frozen baseline. Seeds `{7,11,22,31,43}`. Budgets 10/30/60s + limited 300s.

Mean vehicles (`c101_21`): **23.6 (10s) → 20.2 (30s) → 18.0 (60s)**.  
Mean vehicles (`r101_21`): **33.4 → 29.6 → 26.2** (BKS ~20).  

Limited 300s runs **did not continue the improvement** (`c101_21` seeds 7/11 → 31/28 veh). Treat as a measured long-horizon pathology to debug (acceptance/elimination under long budgets), not as a success.

## Go / no-go

| Gate | Status |
|------|--------|
| CI / partition integrity / attribution | **Go** |
| Classical recovery toward competitive EVRPTW | **Partial go** (best mean ~18–19 veh @60s vs ~11 BKS) |
| Related destroy benefit | **No-go on this panel** |
| LLM insertion-policy discovery now | **No-go** (0/8 headroom vs frozen) |
| Multi-agent / transfer now | **No-go** |

## Reproduce

```powershell
uv sync --locked
uv run pytest -q
uv run ruff check src tests
uv run mypy src/evrptw_autolab
uv run voltforge datasets validate
uv run python scripts/measure_repair_scoring_overhead.py
uv run python scripts/experiment_classical_bottleneck.py
uv run python scripts/experiment_classical_components.py
uv run python scripts/experiment_classical_components_v2.py
uv run python scripts/experiment_headroom_vs_baseline.py
uv run python scripts/experiment_headroom_vs_c4.py
uv run python scripts/experiment_anytime_scalability.py
```

## Next sprint recommendation

1. Debug **300s regression** vs 60s anytime.
2. Stabilize route elimination across seeds (still high variance).
3. Measure headroom for **route-elimination target selection** and **destroy choice**, not insertion ranking.
4. Import/validate a published `c101_21` route under matching contracts if obtainable.
5. Keep LLM gated until a non-insertion residual signal is shown.

## Negative / unresolved

- Still far from BKS on large Schneider instances.
- Related/Shaw destroy implemented but not beneficial here.
- 300s anytime regression unexplained.
- C6 charging arm skipped for Schneider full-recharge.
- No live LLM campaign (by evidence gate).

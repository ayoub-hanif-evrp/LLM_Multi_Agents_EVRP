# VoltForge 2.0 — Research Readiness Report

**Date:** 2026-10-15  
**Baseline commit reviewed:** `6925de8e5444`  
**Working tree:** uncommitted targeted-repair changes on top of `6925de8` (see §2).

## 1. Verdict

| Layer | Status |
|---|---|
| Classical backbone feasibility (14-instance seed-7 panel) | **14/14 feasible** (was 9/14) |
| Evaluator independence / fleet counting | Fixed + regression tested |
| Objective-aware ALNS + deadline | Implemented |
| Component interfaces + fallback attribution | Implemented |
| CV-MAPE evolution (FakeBackend) | Implemented + tested |
| Real Qwen3-Coder multi-agent research claim | **Not yet** — no fair LLM-vs-classical comparison completed in this session |

**Engineering success:** yes — multi-variant evaluation and classical solving are reproducible.  
**Research success (LLM multi-agent superiority):** **not claimed**. Pipeline existence ≠ demonstrated improvement over controlled baselines.

## 2. Files changed (this repair wave)

**Backbone**

- `backbone/energy_repair.py` — multi-candidate station insertion, TW-safe acceptance, Bezzi multi-stop progress, depot-side inserts
- `backbone/route_split.py` — fleet-aware route peeling
- `backbone/nonlinear_charge.py` — partial SoC targets for Montoya
- `backbone/solver.py` — unified `repair_feasibility`, wall-clock deadline
- `backbone/alns.py` — variant `objective_key` acceptance, finite dues, incumbent preserve
- `backbone/local_search.py` — atomic route/assignment drops, PD pair relocate
- `backbone/construct.py` — finite due normalization
- `problem/v2/evaluator.py` — fleet count from every resolved route

**Components / evolution**

- `components/interfaces.py` — finite due sentinel, safe defaults
- `components/run.py` — explicit fallback attribution + source hashes
- `components/evolution/` — archive, fitness, multi-generation engine, freeze bundle

**Tests / results**

- `tests/test_feasibility_repairs.py`
- `tests/test_evolution.py`
- `tests/test_evaluator_v2.py` (fleet omission adversarial)
- `results/v2/baselines/classical/checkpoint_6925de8_seed7.json` (preserved 9/14)
- `results/v2/baselines/classical/run_6925de8_seed7_20261015T203302Z/` (**14/14**)

## 3. Tests run

```text
uv run pytest tests/test_feasibility_repairs.py tests/test_classical_backbone.py \
  tests/test_evaluator_v2.py::test_fleet_counts_resolved_routes_without_assignment_list -q
# 13 passed

uv run pytest tests/test_evolution.py tests/test_component_synthesis.py -q
# 7 passed
```

## 4. Before / after feasibility (seed 7, same 14 instances)

| Instance | Before (`6925de8`) | After |
|---|---|---|
| c101C5 | ✓ | ✓ |
| c103C5 | ✓ | ✓ |
| r104C5 | ✓ | ✓ |
| r105C5 | ✗ WINDOW | ✓ |
| rc105C5 | ✓ | ✓ |
| tc0c10s2cf1 | ✗ BATTERY | ✓ |
| tc0c10s3cf1 | ✗ BATTERY | ✓ |
| C101-5 | ✓ | ✓ |
| R105-5 | ✗ CHARGE_POLICY | ✓ |
| 10-N10 | ✓ | ✓ |
| c101C6 | ✓ | ✓ |
| r104C6 | ✓ | ✓ |
| rc105C6 | ✗ WINDOW | ✓ |
| c101_21 | ✓ | ✓ |
| **Total** | **9/14** | **14/14** |

Preserved checkpoint: `results/v2/baselines/classical/checkpoint_6925de8_seed7.json`.  
New run: `results/v2/baselines/classical/run_6925de8_seed7_20261015T203302Z/`.

## 5. Objective quality notes

- Schneider panel mean vehicles improved (1.8 vs prior ~2.2 on the repaired set).
- Montoya feasible with operating time ≈ 31.3 h total (5 vehicles on 10-customer instances — feasible but not competitive).
- Hiermann `c101_21` still ≈ 4212 with 20 vehicles — feasible, not BKS-competitive.
- Bezzi Dataset A feasible with explicit charge decisions; costs use documented `f` calibration.

## 6. Defects confirmed and fixed

1. Station insertion never searched after-depot positions → Montoya single-customer routes unrepairable.
2. Energy repair accepted battery fixes that broke time windows → Goeke `rc105C6`.
3. Single insertion candidate preferred useless early stations → Goeke `r104C6` regression.
4. Route split ignored fleet limits → Bezzi `C101-5` FLEET regression.
5. Bezzi multi-insert rejected when DP violation counts rose temporarily.
6. ALNS SA scored on distance across incompatible objectives.
7. Fleet availability undercounted when `vehicle_assignments` omitted.
8. Local search dropped empty routes without aligning assignments.
9. Infinite `due_time` poisoned component scorers / removal priorities.
10. LLM fallback to `DEFAULT_SOURCES` was not explicitly attributed.

## 7. Variants that remain difficult (quality)

- **Montoya:** feasibility solved via aggressive splitting; total operating time not optimized.
- **Hiermann:** heterogeneous cost / fleet composition barely explored.
- **Large instances:** outside the 14-instance development panel.

## 8. Real LLM experiments

`qwen3-coder:30b` is installed locally via Ollama.

**Bounded smoke (not a research campaign):**

```bash
uv run voltforge components smoke --ollama --profile qwen3_coder_30b --seed 0
```

Measured: feasible micro_g2; `llm_calls=5`; `wall_s≈29.4`; `genuine_llm_components=1`; `default_heuristic_count=2` (insertion/station fell back after syntax errors in model output — correctly attributed, not counted as LLM discoveries).

**No multi-hour ablation campaign was launched.** Approve before classical vs 1-agent vs 5-agent vs evolution runs.

## 9. Attribution of gains

All 9→14 feasibility gains are from **classical** repair (energy multi-insert, TW-safe charging, route split, PD relocate, charge DP wiring).  
No LLM component discovery is credited for the pilot improvement.

## 10. Remaining limitations

- Development panel still includes `rc105C5` (RC family leakage risk vs older Schneider protocol); a new frozen split is still required before model selection.
- Ablation table (classical / 1-agent / 5-agent / evolution ± critic ± memory) not yet measured with real LLM budgets.
- Paper figures/CSV for gaps vs published BKS not regenerated for the 14/14 run beyond pilot JSON.

## 11. Reproducibility commands

```bash
# Classical panel (seed 7)
uv run voltforge baselines pilot --seed 7

# Regression tests
uv run pytest tests/test_feasibility_repairs.py tests/test_evolution.py tests/test_component_synthesis.py -q

# Fake evolution
uv run python -c "from pathlib import Path; from evrptw_autolab.components.evolution import EvolutionConfig, run_evolution; from evrptw_autolab.llm.registry import FakeBackend; from evrptw_autolab.components.interfaces import DEFAULT_SOURCES; from evrptw_autolab.problem.micro import micro_g1_one_customer; from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2; import json; b=FakeBackend({'routing':json.dumps({'code':DEFAULT_SOURCES['insertion_score']}),'charging':json.dumps({'code':DEFAULT_SOURCES['station_score']}),'search':json.dumps({'code':DEFAULT_SOURCES['removal_priority']})}); print(run_evolution([load_schneider_v2(micro_g1_one_customer().metadata['source_path'])], b, EvolutionConfig(generations=1, work_dir=Path('workspace/evo_smoke'))))"
```

Compare against `checkpoint_6925de8_seed7.json` before claiming regressions.

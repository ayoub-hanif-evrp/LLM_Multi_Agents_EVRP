# VoltForge 2.0 — Research Readiness Report

**Date:** 2026-10-16  
**Pushed repair commit:** `d18fe0edd6f8` (14/14 classical pilot)  
**This document tracks subsequent integrity work on top of that commit.**

## 1. Verdict (honest layers)

| Layer | Status |
|---|---|
| Mathematical formulation validation | Prior Bezzi/objective work; not reopened here |
| Engineering tests / CI | Ruff + pytest + mypy required green |
| Classical solver feasibility (seed-7, 14-dev panel) | **14/14** at `d18fe0e`; **42/42** on seeds 7/11/22 at `200bb9f` |
| Classical objective quality | Improved Montoya on seeds 11/22 (~25.4 vs 31.3); Bezzi/Hiermann gaps remain |
| Solver budgets | Multi-seed deadline report: 38/42 within +0.25s; max overshoot ≈1.05s (was ~29s on Hiermann) |
| Evolution fitness scientific validity | **Paired win/tie/loss + normalized gaps** across panel instances |
| Component lineage / repair attribution | Lineage across crossover; repair success after panel eval |
| Quality-focused Critic | Invoked on stagnation / regression, not only infeasibility |
| Cross-variant transfer | Capability-aware retrieve + accept/reject effect logging |
| Real LLM synthesis | Qwen expressions validate; they do not improve objectives |
| Multi-agent causal contribution | **Not demonstrated** — matched run `campaign_20261016T200013Z` |
| Held-out generalization | **Not run** |
| Publication readiness | **Not ready** for an algorithm-design claim |

**Engineering success:** classical multi-variant solving is reproducible.  
**Research success (LLM multi-agent superiority):** **not claimed**.

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

**Matched campaign CLI (FakeBackend by default — plumbing only):**

```bash
# Cheap fake plumbing check (not a paper result)
uv run voltforge experiments campaign --fake --max-instances 3 --seed 7

# Live open-weight comparison (requires local Ollama + profile installed)
uv run voltforge experiments campaign --ollama --profile qwen3_coder_30b --max-instances 0 --seed 7 --time-limit 8 --generations 2
```

Arms: `classical`, `single_agent`, `five_agent`, `five_agent_evolution`.  
Outputs: `results/v2/campaigns/campaign_<utc>/campaign.json` + `rows.jsonl` with feasibility, objectives, attribution, tokens, wall time.

**Live Qwen, expression contract, 2026-10-16:** `results/v2/campaigns/campaign_20261016T200013Z`. Model `qwen3-coder:30b`, seed 7, 5 development instances, 5-second process kill. Arms: classical, single agent, five agents. No evolution arm. Tokens are run-level: single agent 3,799 (5 instance runs), five agents 7,302 (5 instance runs). Every generated component was an accepted expression (`genuine_llm_components=3`), not a default fallback.

No feasible objective improved on classical. Schneider `c101C5` and Goeke `c101C6`: classical and five-agent `(2, 267.329)`; single agent `(2, 270.986)`. Montoya `tc0c10s2cf1`: classical and five-agent duration `32.115` (4 vehicles, feasible); single agent duration `17.618` but infeasible. Bezzi `C101-5`: all three arms recharge cost `233`. Hiermann `c101_21`: all three arms infeasible. The solver was killed at 5.9s and returned an empty route (1 vehicle, distance 0, penalty objective 153, fault `VISIT: never served`). That 153 is not a solved Hiermann cost. Earlier feasible Hiermann runs exceeded this budget.

FakeBackend rows remain plumbing-only. Do not sum tokens by repeating a run total on every instance row.

## 9. Attribution of gains

All 9→14 feasibility gains are from **classical** repair (energy multi-insert, TW-safe charging, route split, PD relocate, charge DP wiring).  
No LLM component discovery is credited for the pilot improvement.

## 10. Remaining limitations

- Development panel still includes `rc105C5` (RC family leakage risk vs older Schneider protocol); a new frozen split is still required before model selection.
- Ablation table (classical / 1-agent / 5-agent / evolution ± critic ± memory) not yet measured with **live** LLM budgets (CLI ready; results not committed).
- Classical quality gaps remain (Montoya duration/fleet, Bezzi recharge cost vs calibrated references, Hiermann cost/fleet); solver now has cooperative + hard outer deadlines with incumbent preserve.
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

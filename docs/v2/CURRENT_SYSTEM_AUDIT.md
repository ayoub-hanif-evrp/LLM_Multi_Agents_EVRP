# VoltForge 2.0 — Current System Audit (Milestone 0)

**Date:** 2026-10-15  
**Protocol boundary:** Legacy Experiment A (`results/paper/`, `final-protocol-v1`) and Experiment B (`results/structured/`, `structured-protocol-v1`) remain frozen scientific artifacts. VoltForge 2.0 work lives under `docs/v2/`, `problem/v2/`, `problem/datasets/`, and `results/v2/`.

## 1. Architecture map (as found)

```
evrptw_autolab/
  problem/          # Legacy Schneider EVRPTW types, physics, evaluator, schneider parser, micro gates
  sandbox/          # Subprocess solver runner + AST static scan + limits
  llm/              # Ollama + OpenAI-compatible backends, registry, usage logs
  agents/           # Five-agent roles (architect/routing/charging/search/critic)
  synthesis/        # Experiment A: from-scratch five-agent curriculum
  structured/       # Experiment B: modular construct/repair/improve/solve + population search
  evolution/        # Patch apply, candidate evaluation helpers
  evaluation/       # Split fidelity / manifests for Schneider
  cli.py            # `voltforge` / `evrptw-autolab` entry points
```

**Trusted path today:** generated `solver.py` → `sandbox.runner.run_solver` (subprocess) → parent `evaluate_solution` (Schneider contract).

**Unsafe path found:** `structured/codegen.py::unit_test_functions` uses in-process `exec()` on generated source (Milestone 1 target).

## 2. Local datasets (filesystem-verified)

| Folder under `dataset/` | Files | Dominant format | Usable instance-like files (pre-parser) |
|-------------------------|-------|-----------------|----------------------------------------|
| `schneider` | 94 | Solomon-style `.txt` | **93** under `raw_instances/` (+ README) |
| `montoya-et-al-2017` | 121 | XML + readme | **120** `.xml` (nonlinear charging) |
| `Bezzi & Ceselli EVRP-MRT` | 265 | XML + PNG | **132** `.xml` (+ 132 PNG + MANIFEST) |
| `goeke-2018` | 93 | Solomon-like `.txt` with `cp`/`cd` + PartnerID | **93** |
| `hiermann-et-al-2017-set-1` | 57 | `.txt` with per-station `rechargingrate` | **57** |

Raw files must remain unchanged. Counts above are file inventory, not validated-import counts.

## 3. Known limitations / failures

1. **Homogeneous EV only** — `VehicleSpec` is a single vehicle type; no fleet composition.
2. **Linear full recharge** — `physics.py` / evaluator assume Euclidean distance, linear consumption, full recharge.
3. **Schneider-coupled sandbox driver** — `_DRIVER` hard-imports `load_instance` from `problem.schneider`.
4. **In-process `exec`** — structured Level-A unit tests execute untrusted code in the controller.
5. **No G4 4/4** — frozen Experiment A and B pilots never reached confirmed Schneider G4 4/4.
6. **Structured curriculum still Schneider/micro** — Level A uses private micro instances; Level B uses Schneider C5 G4.
7. **Frontier OpenAI-compatible profiles** — present for Experiment B; VoltForge 2.0 research mandate is **local Ollama only**.
8. **Ollama content vs thinking** — current client treats empty `message.content` as failure but does not separately record `message.thinking` or reject thinking-only replies as solver code.

## 4. Installed Ollama models (this workstation)

Verified via `ollama list` at audit time:

- Primary: `qwen3-coder:30b`, `glm-4.7-flash:latest`, `devstral-small-2:24b`, `gpt-oss:20b`
- Additional: `phi4-reasoning:14b`, `deepseek-r1:14b`, `qwen2.5-coder:14b`, `qwen2.5-coder:7b`, `deepseek-coder:6.7b`, `codellama:7b`, other Qwen/Llama variants

Hardware: RTX A5000 24 GB, 32 GB RAM, Windows 11. Default `num_ctx=8192` for large models.

## 5. Compatibility risks

- Extending `EVRPTWInstance` in place would break frozen Experiment A/B evaluators → use `problem/v2/` + adapters.
- Changing Schneider evaluator semantics would invalidate historical results → keep legacy evaluator frozen; add variant-aware oracle beside it.
- Claiming “sandbox security” from AST scan alone is incorrect; document residual risk (ordinary subprocess ≠ hardened jail).

## 6. Migration plan

| Milestone | Deliverable | Legacy impact |
|-----------|-------------|---------------|
| M0 | This audit | None |
| M1 | Safe subprocess unit tests; Ollama thinking/token/show hardening | Structured path only |
| M2 | Dataset registry + parsers + manifests (**done**: all five families validate to ProblemSpecV2) | Additive |
| M3 | Variant-aware evaluator (`problem/v2/evaluator.py`) | Additive; Schneider legacy regression required |
| M4 | Classical backbone (construction/ALNS) — **done** under `backbone/` | Additive |
| M5–M8 | Multi-agent CV-MAPE, experiments under `results/v2/` | New protocol IDs |

## 7. Milestone 0 exit criteria

- [x] Five dataset folders located and counted
- [x] Unsafe `exec` location identified
- [x] Architecture map written
- [x] Explicit legacy vs v2 boundary stated

# Handoff — continue on another PC

Do **not** rely on Cursor chat history. This file + `results/md/SLM_EVO_STATUS.md` are the source of truth.

## Clone and setup

```bash
git clone https://github.com/ayoub-hanif-evrp/LLM_Multi_Agents_EVRP.git
cd LLM_Multi_Agents_EVRP
uv sync
# or: python -m venv .venv && .venv\Scripts\activate && pip install -e .
uv run pytest -q
```

For SLM-Evo LLM runs: install **Ollama**, pull `qwen2.5-coder:14b` (profile `qwen25_coder_14b` in `configs/models.yaml`).

## Hard rules (do not break)

- **Never modify** frozen MCB V1 (`src/evrptw_autolab/build/minimal_cooperative_build_v1.py`) or its protocol/results.
- **Never overwrite** `results/md/artifacts/slm_evo/OPT_V1/`.
- Unlock prompts only — **no** ALNS / savings / route-merging / GA / VNS / tabu naming in agent instructions.
- After evolution, deployment stays **zero LLM calls**.
- BEST promotion requires **all 12 C5 fully feasible** (gate already in `slm_evo/evolve.py`).

## Scientific story so far

1. **MCB V1 synthesis:** Qwen2.5-Coder 14B seed33 → first from-scratch G4 4/4 → **12/12 C5**, ~**60** vehicles (one route / customer + station insert). Artifact: `results/md/artifacts/mcb_v1/FEASIBLE_SYNTHESIZED_SOLVER_V0_qwen14b_seed33/`.
2. **Full-rewrite opt pilot failed** (runtime crashes). Replaced by **SLM-Evo**: small AST patches + parallel roles + deterministic eval.
3. **OPT_V1:** first fleet win → **53** veh / 12/12. Immutable: `results/md/artifacts/slm_evo/OPT_V1/`.
4. **From 60 parent, 5 seeds:** 2/5 valid improvements to **55** (seed 11/33). Continuation toward “24” was **invalid** (10/12) — do **not** resume that solver.
5. **From OPT_V1 (53), 5 seeds, 12/12 gate:** **5/5** improved. Best **OPT_V2** = **30** veh / 12/12 (seed 22). Path: `results/md/artifacts/slm_evo/OPT_V2_09ee68b15c8d2906/`.

Key reports:

- `results/md/SLM_EVO_STATUS.md`
- `results/md/SLM_EVO_OPT_V1_5SEED_REPORT.md`
- `results/md/SLM_EVO_OPT_REPRO_5SEED_REPORT.md` (60→55 campaign)

## Immediate next experiment (only this)

**Scale-aware SLM-Evo** starting from **OPT_V2** (30 / 12/12):

1. Keep C5 12/12 gate.
2. Add a **fixed small C10/C15 development subset** into selection pressure (accept only if still feasible on that subset — no metaheuristic hints).
3. Run a short multi-seed or single continuation campaign; freeze best as e.g. `OPT_V3_*` (never touch OPT_V1/OPT_V2).
4. **Held-out eval** on larger Schneider instances not used in development (reuse `scripts/eval_slm_evo_scale.py` pattern).
5. Then write the paper (synthesis + autonomous evolution claim).

Do **not** chase invalid low vehicle counts that break 12/12 or generalization.

## Useful commands

```bash
# Single SLM-Evo run
uv run python scripts/run_slm_evo.py --profile qwen25_coder_14b --parent results/md/artifacts/slm_evo/OPT_V2_09ee68b15c8d2906/solver.py --run-id scale01 --seed 11

# Multi-seed campaign (example flags from last OPT_V1 run)
uv run python scripts/run_slm_evo_seed_campaign.py --profile qwen25_coder_14b --parent results/md/artifacts/slm_evo/OPT_V1/solver.py --run-prefix from53_s --best-tag OPT_V2

# Scale eval only (no LLM)
uv run python scripts/eval_slm_evo_scale.py --solver results/md/artifacts/slm_evo/OPT_V2_09ee68b15c8d2906 --sizes 10,15 --tag opt_v2
```

## Prompt for Cursor on the new PC

> Continue VoltForge / SLM-Evo from `NEXT.md` and `results/md/SLM_EVO_STATUS.md`. Start scale-aware evolution from OPT_V2 (30 veh / 12/12). Do not modify MCB V1 or overwrite OPT_V1. Keep the all-C5 12/12 gate; add a fixed C10/C15 development subset to selection pressure; no metaheuristic names in prompts.

# FINAL reproducibility

- Python: `3.14.4`
- Platform: `Windows-11-10.0.26200-SP0`
- Ollama: `ollama version is 0.33.3`
- GPU/HW: `NVIDIA RTX A2000 12GB, 12282 MiB`
- Models: `qwen2.5-coder:7b`, `deepseek-coder:6.7b`, `codellama:7b`, `deepseek-coder-v2:16b`
- Protocol synthesis: `MINIMAL_COOPERATIVE_BUILD_V1` (frozen)
- Protocol baseline: `SINGLE_AGENT_MATCHED_V1`
- Protocol repair: `P1.3_REGRESSION_SAFE` (frozen)
- Seeds: `11,22,33,44,55`
- Temperatures (MCB defaults): architect 0.35, coding 0.25, critic 0.10; single-agent 0.25
- Context: `num_ctx<=4096` in runners
- Token budgets (single-agent matched to Qwen MCB): 18179/39157/23579/6205/18207
- Gates: G0 executable, G1 one-customer, G2 charging micro, G3 two-customer, G4 Schneider panel c101C5/c103C5/r104C5/r105C5
- Optimization: LOCKED unless from-scratch G4=4/4 appears
- Common repair seed: `results/md/artifacts/p1_minimal/FEASIBLE_SOLVER_V0_solver.py`
- Historical DeepSeek repair freeze: `results/md/artifacts/p1_3/P1_3_FIRST_4OF4_SOLVER/`

## Key artifact paths

- MCB seeded: `results/md/tables/raw_autolab/discovery_mcb_v1_*_seed*.json`
- Single-agent: `results/md/tables/raw_autolab/discovery_single_agent_v1_*`
- Repair seeded: `results/md/tables/raw_autolab/discovery_p1_3_*_repair_seed*.json`
- Workspaces: `workspace/discovery_mcb_v1/`, `workspace/discovery_single_agent_v1/`, `workspace/discovery_p1_3/`

# Experiment B — Empty-workspace five-agent synthesis

**Model:** `deepseek-coder:6.7b` (`deepseek_coder_67b`)
**Run id:** `synth01`
**Empty at start:** True | **Seed provided:** False
**Stopped:** G2_FAIL
**G4:** 0/4 | **G4 PASS:** False
**Wall:** 234.99111959990114s | **LLM calls:** 20 | **prompt_tokens:** 44091 | **completion_tokens:** 8705
**Solver hash:** `36eac1da8bad9cad`

## Success levels (predefined)

- **B0_executable:** True
- **B1_G1_G3:** False
- **B2_at_least_1_of_4_G4:** False
- **B3_G4_4_of_4:** False
- **B4_all_C5_ge_10_of_12:** False
- **Strong_B_12_of_12:** False

## Gates

- **G0:** PASS — contract_ok
- **G1:** PASS — feasible
- **G2:** FAIL — CRASH

## All Schneider C5 (unchanged): 0/12

- `c101C5`: CRASH
- `c103C5`: CRASH
- `c206C5`: CRASH
- `c208C5`: CRASH
- `r104C5`: CRASH
- `r105C5`: CRASH
- `r202C5`: CRASH
- `r203C5`: CRASH
- `rc105C5`: CRASH
- `rc108C5`: CRASH
- `rc204C5`: CRASH
- `rc208C5`: CRASH

## Instance-specific audit

- constants: **NONE**
- hardcoded C/S literals: []
- mechanism: likely dedicated or constructive routes; uses propagate_route for feasibility checks

**solver:** `C:\Users\AYOUB\OneDrive - EMSI\Bureau\PHD_WORK\LLM_Multi_Agents_EVRP\workspace\discovery_p1_b\deepseek_coder_67b\synth01\current\solver.py`

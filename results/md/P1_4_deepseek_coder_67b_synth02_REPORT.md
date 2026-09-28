# P1.4 Code-Integrity-Safe Synthesis

**Model:** `deepseek-coder:6.7b` | **run_id:** `synth02`
**Empty at start:** True | **Seed:** none
**Stopped:** G2_FAIL
**G4:** 0/4 | **PASS:** False
**Calls:** 18 | **tokens:** 37614/7751 | **wall:** 206.1s
**Commit rejections (invalid candidates blocked):** 0

## Success levels

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

## Audit: FOUND | ast_valid=True

Checkpoints: `C:\Users\AYOUB\OneDrive - EMSI\Bureau\PHD_WORK\LLM_Multi_Agents_EVRP\workspace\discovery_p1_4\deepseek_coder_67b\synth02\checkpoints`
Post-mortem (synth01): `results/md/P1_B_synth01_POSTMORTEM.md`

# MINIMAL_COOPERATIVE_BUILD_V1

**Model:** `deepseek-coder:6.7b` | **run_id:** `synth04`
**Stopped:** G2_FAIL
**G4:** 0/4 | **PASS:** False
**Calls:** 12 | **tokens:** 25963/4459 | **wall:** 125.6s
**Roles invoked:** ['architect', 'charging', 'critic', 'routing', 'search']
**Team incomplete orchestration:** False
**Primary failure:** {'failure_class': 'FEASIBILITY', 'role': 'team', 'gate': 'G2', 'detail': 'BATTERY'}
**Taxonomy:** {'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 1, 'GENERALITY': 0, 'FEASIBILITY': 4, 'OPTIMIZATION': 0, 'NO_OP': 0}

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
- **G2:** FAIL — BATTERY

**Committed hashes:** ['797263e12916d9be', '4a40c1421b388082', '918f166cd9a2ad5c', '30b65d4aafd29e25', 'ac11b43b85a55443', '918f166cd9a2ad5c']

# MINIMAL_COOPERATIVE_BUILD_V1

**Model:** `qwen2.5-coder:7b` | **run_id:** `seed22` | **llm_seed:** `22`
**Stopped:** PARTIAL_G4_2
**G4:** 2/4 | **PASS:** False
**Calls:** 21 | **tokens:** 34851/4306 | **wall:** 134.8s
**Roles invoked:** ['architect', 'charging', 'critic', 'routing']
**Team incomplete orchestration:** False
**Primary failure:** {'failure_class': 'FEASIBILITY', 'role': 'team', 'gate': 'G4', 'detail': 'BATTERY'}
**Taxonomy:** {'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 0, 'GENERALITY': 0, 'FEASIBILITY': 9, 'OPTIMIZATION': 0, 'NO_OP': 0}
**Mechanism diversity (reporting):** {'algo_drafts': 9, 'charging_algo_drafts': 9, 'feasibility_families_seen': ['BATTERY'], 'committed_hash_count': 11, 'distinct_committed_hashes': 6}

## Success levels

- **B0_executable:** True
- **B1_G1_G3:** True
- **B2_at_least_1_of_4_G4:** True
- **B3_G4_4_of_4:** False
- **B4_all_C5_ge_10_of_12:** False
- **Strong_B_12_of_12:** False

## Gates

- **G0:** PASS — contract_ok
- **G1:** PASS — feasible
- **G2:** PASS — feasible
- **G3:** PASS — feasible
- **G4:** FAIL — PARTIAL 2/4 final={'c101C5': 'OK', 'c103C5': 'OK', 'r104C5': 'BATTERY', 'r105C5': 'BATTERY'}

**Committed hashes:** ['ccfeaedd9b890e08', '45d733dfe00f2902', '728e04603a64d89d', '3d20c2cba9be1096', '9ba6fe5256e07458', 'f7c44f85cc4e4301', 'f7c44f85cc4e4301', 'f7c44f85cc4e4301', 'f7c44f85cc4e4301', 'f7c44f85cc4e4301', 'f7c44f85cc4e4301']

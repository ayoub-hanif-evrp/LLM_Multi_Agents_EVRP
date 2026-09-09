# MINIMAL_COOPERATIVE_BUILD_V1

**Model:** `qwen2.5-coder:7b` | **run_id:** `seed11` | **llm_seed:** `11`
**Stopped:** PARTIAL_G4_3
**G4:** 3/4 | **PASS:** False
**Calls:** 11 | **tokens:** 16565/1614 | **wall:** 56.9s
**Roles invoked:** ['architect', 'charging', 'critic', 'routing']
**Team incomplete orchestration:** False
**Primary failure:** {'failure_class': 'FEASIBILITY', 'role': 'team', 'gate': 'G4', 'detail': 'BATTERY'}
**Taxonomy:** {'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 0, 'GENERALITY': 0, 'FEASIBILITY': 4, 'OPTIMIZATION': 0, 'NO_OP': 0}
**Mechanism diversity (reporting):** {'algo_drafts': 4, 'charging_algo_drafts': 4, 'feasibility_families_seen': ['BATTERY'], 'committed_hash_count': 6, 'distinct_committed_hashes': 2}

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
- **G4:** FAIL — PARTIAL 3/4 final={'c101C5': 'OK', 'c103C5': 'OK', 'r104C5': 'OK', 'r105C5': 'BATTERY'}

**Committed hashes:** ['dd260089b1bb485a', 'd6bb30ca0ec853b2', 'd6bb30ca0ec853b2', 'd6bb30ca0ec853b2', 'd6bb30ca0ec853b2', 'd6bb30ca0ec853b2']

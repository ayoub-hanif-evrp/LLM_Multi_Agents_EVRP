# MINIMAL_COOPERATIVE_BUILD_V1

**Model:** `qwen2.5-coder:7b` | **run_id:** `seed33` | **llm_seed:** `33`
**Stopped:** PARTIAL_G4_3
**G4:** 3/4 | **PASS:** False
**Calls:** 13 | **tokens:** 20507/3072 | **wall:** 95.0s
**Roles invoked:** ['architect', 'charging', 'critic', 'routing']
**Team incomplete orchestration:** False
**Primary failure:** {'failure_class': 'FEASIBILITY', 'role': 'team', 'gate': 'G4', 'detail': 'BATTERY'}
**Taxonomy:** {'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 0, 'GENERALITY': 0, 'FEASIBILITY': 5, 'OPTIMIZATION': 0, 'NO_OP': 0}
**Mechanism diversity (reporting):** {'algo_drafts': 5, 'charging_algo_drafts': 5, 'feasibility_families_seen': ['BATTERY'], 'committed_hash_count': 7, 'distinct_committed_hashes': 6}

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

**Committed hashes:** ['dd260089b1bb485a', '6583f1b5ad08c6d9', 'a693a0d11e3c9cb9', '40cf095be2d7abe1', 'c85afb9ff0820e5e', '77aa5840c86d4ca6', '77aa5840c86d4ca6']

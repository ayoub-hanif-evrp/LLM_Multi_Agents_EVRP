# MINIMAL_COOPERATIVE_BUILD_V1

**Model:** `qwen2.5-coder:7b` | **run_id:** `screen01`
**Stopped:** CODING_FAILURE
**G4:** 0/4 | **PASS:** False
**Calls:** 7 | **tokens:** 9229/810 | **wall:** 29.4s
**Roles invoked:** ['architect', 'charging', 'critic', 'routing', 'search']
**Team incomplete orchestration:** False
**Primary failure:** {'failure_class': 'GENERALITY', 'role': 'search', 'gate': 'G2', 'detail': "HARDCODED_INSTANCE_IDENTIFIER: ['S0']"}
**Taxonomy:** {'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 0, 'GENERALITY': 3, 'FEASIBILITY': 1, 'OPTIMIZATION': 0, 'NO_OP': 0}
**Mechanism diversity (reporting):** {'algo_drafts': 1, 'charging_algo_drafts': 1, 'feasibility_families_seen': ['BATTERY'], 'committed_hash_count': 2, 'distinct_committed_hashes': 1}

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
- **G2:** FAIL — CODING_FAILURE:GENERALITY/search:HARDCODED_INSTANCE_IDENTIFIER: ['S0']

**Committed hashes:** ['dd260089b1bb485a', 'dd260089b1bb485a']

# MINIMAL_COOPERATIVE_BUILD_V1

**Model:** `codellama:7b` | **run_id:** `screen01`
**Stopped:** G2_FAIL
**G4:** 0/4 | **PASS:** False
**Calls:** 11 | **tokens:** 17105/2505 | **wall:** 67.7s
**Roles invoked:** ['architect', 'charging', 'critic', 'routing']
**Team incomplete orchestration:** False
**Primary failure:** {'failure_class': 'FEASIBILITY', 'role': 'team', 'gate': 'G2', 'detail': 'VISIT'}
**Taxonomy:** {'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 0, 'GENERALITY': 0, 'FEASIBILITY': 4, 'OPTIMIZATION': 0, 'NO_OP': 0}
**Mechanism diversity (reporting):** {'algo_drafts': 4, 'charging_algo_drafts': 4, 'feasibility_families_seen': ['DEPOT', 'VISIT'], 'committed_hash_count': 6, 'distinct_committed_hashes': 3}

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
- **G2:** FAIL — VISIT

**Committed hashes:** ['ccfeaedd9b890e08', '4d4a261d75573ec1', 'f78b58b0e5aa5888', 'f78b58b0e5aa5888', 'f78b58b0e5aa5888', 'f78b58b0e5aa5888']

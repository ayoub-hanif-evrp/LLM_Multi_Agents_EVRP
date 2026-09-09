# MINIMAL_COOPERATIVE_BUILD_V1

**Model:** `codellama:7b` | **run_id:** `seed33` | **llm_seed:** `33`
**Stopped:** G4_FAIL
**G4:** 0/4 | **PASS:** False
**Calls:** 35 | **tokens:** 69339/5469 | **wall:** 187.8s
**Roles invoked:** ['architect', 'charging', 'critic', 'routing']
**Team incomplete orchestration:** False
**Primary failure:** {'failure_class': 'FEASIBILITY', 'role': 'team', 'gate': 'G4', 'detail': 'BATTERY'}
**Taxonomy:** {'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 0, 'GENERALITY': 0, 'FEASIBILITY': 16, 'OPTIMIZATION': 0, 'NO_OP': 0}
**Mechanism diversity (reporting):** {'algo_drafts': 16, 'charging_algo_drafts': 16, 'feasibility_families_seen': ['BATTERY'], 'committed_hash_count': 18, 'distinct_committed_hashes': 2}

## Success levels

- **B0_executable:** True
- **B1_G1_G3:** True
- **B2_at_least_1_of_4_G4:** False
- **B3_G4_4_of_4:** False
- **B4_all_C5_ge_10_of_12:** False
- **Strong_B_12_of_12:** False

## Gates

- **G0:** PASS — contract_ok
- **G1:** PASS — feasible
- **G2:** PASS — feasible
- **G3:** PASS — feasible
- **G4:** FAIL — PARTIAL 0/4 final={'c101C5': 'BATTERY', 'c103C5': 'BATTERY', 'r104C5': 'BATTERY', 'r105C5': 'BATTERY'}

**Committed hashes:** ['ccfeaedd9b890e08', 'ebf2dc3cdad6c8b6', 'ebf2dc3cdad6c8b6', 'ebf2dc3cdad6c8b6', 'ebf2dc3cdad6c8b6', 'ebf2dc3cdad6c8b6', 'ebf2dc3cdad6c8b6', 'ebf2dc3cdad6c8b6', 'ebf2dc3cdad6c8b6', 'ebf2dc3cdad6c8b6', 'ebf2dc3cdad6c8b6', 'ebf2dc3cdad6c8b6', 'ebf2dc3cdad6c8b6', 'ebf2dc3cdad6c8b6', 'ebf2dc3cdad6c8b6', 'ebf2dc3cdad6c8b6', 'ebf2dc3cdad6c8b6', 'ebf2dc3cdad6c8b6']

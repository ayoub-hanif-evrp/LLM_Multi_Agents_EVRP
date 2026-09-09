# MINIMAL_COOPERATIVE_BUILD_V1

**Model:** `codellama:7b` | **run_id:** `seed44` | **llm_seed:** `44`
**Stopped:** CODING_FAILURE
**G4:** 0/4 | **PASS:** False
**Calls:** 5 | **tokens:** 8851/2023 | **wall:** 51.5s
**Roles invoked:** ['architect', 'charging', 'routing', 'search']
**Team incomplete orchestration:** False
**Primary failure:** {'failure_class': 'GENERALITY', 'role': 'search', 'gate': 'G2', 'detail': "HARDCODED_INSTANCE_IDENTIFIER: ['S0']"}
**Taxonomy:** {'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 0, 'GENERALITY': 3, 'FEASIBILITY': 0, 'OPTIMIZATION': 0, 'NO_OP': 0}
**Mechanism diversity (reporting):** {'algo_drafts': 0, 'charging_algo_drafts': 0, 'feasibility_families_seen': [], 'committed_hash_count': 1, 'distinct_committed_hashes': 1}

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

**Committed hashes:** ['ccfeaedd9b890e08']

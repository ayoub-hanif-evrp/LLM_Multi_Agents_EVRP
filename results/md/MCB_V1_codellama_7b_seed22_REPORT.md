# MINIMAL_COOPERATIVE_BUILD_V1

**Model:** `codellama:7b` | **run_id:** `seed22` | **llm_seed:** `22`
**Stopped:** CODING_FAILURE
**G4:** 0/4 | **PASS:** False
**Calls:** 2 | **tokens:** 2877/324 | **wall:** 9.2s
**Roles invoked:** ['architect', 'routing']
**Team incomplete orchestration:** True
**Primary failure:** {'failure_class': 'FORMAT', 'role': 'routing', 'gate': 'G0', 'detail': 'missing def solve'}
**Taxonomy:** {'FORMAT': 1, 'SYNTAX': 0, 'RUNTIME': 0, 'GENERALITY': 0, 'FEASIBILITY': 0, 'OPTIMIZATION': 0, 'NO_OP': 0}
**Mechanism diversity (reporting):** {'algo_drafts': 0, 'charging_algo_drafts': 0, 'feasibility_families_seen': [], 'committed_hash_count': 0, 'distinct_committed_hashes': 0}

## Success levels

- **B0_executable:** False
- **B1_G1_G3:** False
- **B2_at_least_1_of_4_G4:** False
- **B3_G4_4_of_4:** False
- **B4_all_C5_ge_10_of_12:** False
- **Strong_B_12_of_12:** False

## Gates

- **G0:** FAIL — CODING_FAILURE:FORMAT/routing:missing def solve

**Committed hashes:** []

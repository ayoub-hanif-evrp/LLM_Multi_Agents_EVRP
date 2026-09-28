# MINIMAL_COOPERATIVE_BUILD_V1

**Model:** `qwen2.5-coder:14b` | **run_id:** `seed11` | **llm_seed:** `11`
**Stopped:** G4_FAIL
**G4:** 0/4 | **PASS:** False
**Calls:** 19 | **tokens:** 33474/4952 | **wall:** 276.5s
**Roles invoked:** ['architect', 'charging', 'critic', 'routing', 'search']
**Team incomplete orchestration:** False
**Primary failure:** {'failure_class': 'FEASIBILITY', 'role': 'team', 'gate': 'G4', 'detail': 'BATTERY'}
**Taxonomy:** {'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 1, 'GENERALITY': 0, 'FEASIBILITY': 8, 'OPTIMIZATION': 0, 'NO_OP': 0}
**Mechanism diversity (reporting):** {'algo_drafts': 8, 'charging_algo_drafts': 7, 'feasibility_families_seen': ['BATTERY', 'VISIT'], 'committed_hash_count': 9, 'distinct_committed_hashes': 3}

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

**Committed hashes:** ['1e837706f16dd3d2', '61643b6881db337d', '4bd755d0861f0801', '4bd755d0861f0801', '4bd755d0861f0801', '4bd755d0861f0801', '4bd755d0861f0801', '4bd755d0861f0801', '4bd755d0861f0801']

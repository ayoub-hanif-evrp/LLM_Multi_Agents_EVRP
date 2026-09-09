# MINIMAL_COOPERATIVE_BUILD_V1

**Model:** `deepseek-coder:6.7b` | **run_id:** `seed33` | **llm_seed:** `33`
**Stopped:** G1_FAIL
**G4:** 0/4 | **PASS:** False
**Calls:** 10 | **tokens:** 16153/3870 | **wall:** 100.2s
**Roles invoked:** ['architect', 'critic', 'routing']
**Team incomplete orchestration:** True
**Primary failure:** {'failure_class': 'FEASIBILITY', 'role': 'team', 'gate': 'G1', 'detail': 'VISIT'}
**Taxonomy:** {'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 0, 'GENERALITY': 0, 'FEASIBILITY': 4, 'OPTIMIZATION': 0, 'NO_OP': 0}
**Mechanism diversity (reporting):** {'algo_drafts': 4, 'charging_algo_drafts': 0, 'feasibility_families_seen': ['VISIT'], 'committed_hash_count': 5, 'distinct_committed_hashes': 5}

## Success levels

- **B0_executable:** True
- **B1_G1_G3:** False
- **B2_at_least_1_of_4_G4:** False
- **B3_G4_4_of_4:** False
- **B4_all_C5_ge_10_of_12:** False
- **Strong_B_12_of_12:** False

## Gates

- **G0:** PASS — contract_ok
- **G1:** FAIL — VISIT

**Committed hashes:** ['1d837a62262c6ee8', '9f113bf4642e09a7', 'd0848519fd813a8a', '6bf5d230c0b07140', '265499184145f81c']

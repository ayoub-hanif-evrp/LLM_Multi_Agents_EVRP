# MINIMAL_COOPERATIVE_BUILD_V1

**Model:** `deepseek-coder:6.7b` | **run_id:** `seed22` | **llm_seed:** `22`
**Stopped:** G2_FAIL
**G4:** 0/4 | **PASS:** False
**Calls:** 11 | **tokens:** 23618/4479 | **wall:** 129.3s
**Roles invoked:** ['architect', 'charging', 'critic', 'routing']
**Team incomplete orchestration:** False
**Primary failure:** {'failure_class': 'FEASIBILITY', 'role': 'team', 'gate': 'G2', 'detail': 'BATTERY'}
**Taxonomy:** {'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 0, 'GENERALITY': 0, 'FEASIBILITY': 4, 'OPTIMIZATION': 0, 'NO_OP': 0}
**Mechanism diversity (reporting):** {'algo_drafts': 4, 'charging_algo_drafts': 4, 'feasibility_families_seen': ['BATTERY'], 'committed_hash_count': 6, 'distinct_committed_hashes': 5}

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
- **G2:** FAIL — BATTERY

**Committed hashes:** ['8cf531890ed3f24d', '38207950aaeaec8a', 'bba3663690a7f04f', 'd07a086b2faf31bc', '8851171ae713f5ea', 'd07a086b2faf31bc']

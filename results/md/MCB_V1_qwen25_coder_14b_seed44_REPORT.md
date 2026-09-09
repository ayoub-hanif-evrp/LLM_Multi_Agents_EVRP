# MINIMAL_COOPERATIVE_BUILD_V1

**Model:** `qwen2.5-coder:14b` | **run_id:** `seed44` | **llm_seed:** `44`
**Stopped:** G4_FAIL
**G4:** 0/4 | **PASS:** False
**Calls:** 18 | **tokens:** 34586/5561 | **wall:** 312.1s
**Roles invoked:** ['architect', 'charging', 'critic', 'routing']
**Team incomplete orchestration:** False
**Primary failure:** {'failure_class': 'FEASIBILITY', 'role': 'team', 'gate': 'G4', 'detail': 'BATTERY'}
**Taxonomy:** {'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 0, 'GENERALITY': 0, 'FEASIBILITY': 8, 'OPTIMIZATION': 0, 'NO_OP': 0}
**Mechanism diversity (reporting):** {'algo_drafts': 8, 'charging_algo_drafts': 7, 'feasibility_families_seen': ['BATTERY', 'VISIT', 'WINDOW'], 'committed_hash_count': 9, 'distinct_committed_hashes': 5}

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
- **G4:** FAIL — PARTIAL 0/4 final={'c101C5': 'WINDOW', 'c103C5': 'WINDOW', 'r104C5': 'BATTERY', 'r105C5': 'WINDOW'}

**Committed hashes:** ['178c59078cc7a278', 'e564c0e385d9bc64', '8ec03adbb6f51aaa', '8ec03adbb6f51aaa', '8ec03adbb6f51aaa', 'd2bbcfef9311c304', 'b05795cee9be4816', 'b05795cee9be4816', 'b05795cee9be4816']

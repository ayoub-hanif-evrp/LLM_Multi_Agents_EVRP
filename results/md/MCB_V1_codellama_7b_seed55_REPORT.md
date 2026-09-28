# MINIMAL_COOPERATIVE_BUILD_V1

**Model:** `codellama:7b` | **run_id:** `seed55` | **llm_seed:** `55`
**Stopped:** CODING_FAILURE
**G4:** 0/4 | **PASS:** False
**Calls:** 6 | **tokens:** 11559/1195 | **wall:** 35.6s
**Roles invoked:** ['architect', 'charging', 'routing', 'search']
**Team incomplete orchestration:** False
**Primary failure:** {'failure_class': 'RUNTIME', 'role': 'search', 'gate': 'G2', 'detail': 'Traceback (most recent call last):\n  File "C:\\Users\\AYOUB\\AppData\\Local\\Temp\\evrptw_autolab_w78s0k6k\\driver.py", line 61, in <module>\n    result = _call_solve()\n  File "C:\\Users\\AYOUB\\AppData\\Local\\Temp\\evrptw_autolab_w78s0k6k\\driver.py", line 26, in _call_solve\n    return solve(instance, **kwargs)\n  File "C:\\Users\\AYOUB\\AppData\\Local\\Temp\\evrptw_p15_1_xog35s\\solver.py", line 14, in solve\n    if energy_required(instance.node_map[next_customer], instance.vehicle) > 0:\n       ~~~~~~~~~~~~~~~^^^^^^'}
**Taxonomy:** {'FORMAT': 0, 'SYNTAX': 1, 'RUNTIME': 3, 'GENERALITY': 0, 'FEASIBILITY': 0, 'OPTIMIZATION': 0, 'NO_OP': 0}
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
- **G2:** FAIL — CODING_FAILURE:RUNTIME/search:Traceback (most recent call last):
  File "C:\Users\AYOUB\AppData\Local\Temp\evrptw_autolab_w78s0k6k\driver.py", line 61, in <module>
    result = _call_solve()
  File "C:\Users\AYOUB\AppData\Local\Temp\evrptw_

**Committed hashes:** ['ccfeaedd9b890e08']

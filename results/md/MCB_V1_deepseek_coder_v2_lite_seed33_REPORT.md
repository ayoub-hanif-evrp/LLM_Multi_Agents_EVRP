# MINIMAL_COOPERATIVE_BUILD_V1

**Model:** `deepseek-coder-v2:16b` | **run_id:** `seed33` | **llm_seed:** `33`
**Stopped:** CODING_FAILURE
**G4:** 0/4 | **PASS:** False
**Calls:** 10 | **tokens:** 18460/2815 | **wall:** 82.1s
**Roles invoked:** ['architect', 'charging', 'critic', 'routing', 'search']
**Team incomplete orchestration:** False
**Primary failure:** {'failure_class': 'RUNTIME', 'role': 'search', 'gate': 'G2', 'detail': 'Traceback (most recent call last):\n  File "C:\\Users\\AYOUB\\AppData\\Local\\Temp\\evrptw_autolab_gcwy526h\\driver.py", line 61, in <module>\n    result = _call_solve()\n  File "C:\\Users\\AYOUB\\AppData\\Local\\Temp\\evrptw_autolab_gcwy526h\\driver.py", line 26, in _call_solve\n    return solve(instance, **kwargs)\n  File "C:\\Users\\AYOUB\\AppData\\Local\\Temp\\evrptw_p15__6zj6a4_\\solver.py", line 31, in solve\n    add_charging_station(routes[i])\n    ~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^\n  File "C:\\Users\\AYOUB\\AppData\\Local'}
**Taxonomy:** {'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 3, 'GENERALITY': 1, 'FEASIBILITY': 2, 'OPTIMIZATION': 0, 'NO_OP': 0}
**Mechanism diversity (reporting):** {'algo_drafts': 2, 'charging_algo_drafts': 2, 'feasibility_families_seen': ['BATTERY'], 'committed_hash_count': 3, 'distinct_committed_hashes': 3}

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
  File "C:\Users\AYOUB\AppData\Local\Temp\evrptw_autolab_gcwy526h\driver.py", line 61, in <module>
    result = _call_solve()
  File "C:\Users\AYOUB\AppData\Local\Temp\evrptw_

**Committed hashes:** ['873bcee57e581e16', '0d459e38cfdc82db', 'ed006709126cd863']

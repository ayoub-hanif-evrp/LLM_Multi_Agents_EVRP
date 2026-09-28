# MINIMAL_COOPERATIVE_BUILD_V1

**Model:** `codellama:7b` | **run_id:** `seed11` | **llm_seed:** `11`
**Stopped:** CODING_FAILURE
**G4:** 0/4 | **PASS:** False
**Calls:** 7 | **tokens:** 14086/1495 | **wall:** 48.1s
**Roles invoked:** ['architect', 'charging', 'critic', 'routing', 'search']
**Team incomplete orchestration:** False
**Primary failure:** {'failure_class': 'RUNTIME', 'role': 'search', 'gate': 'G2', 'detail': 'Traceback (most recent call last):\n  File "C:\\Users\\AYOUB\\AppData\\Local\\Temp\\evrptw_autolab_z2h1wmt2\\driver.py", line 61, in <module>\n    result = _call_solve()\n  File "C:\\Users\\AYOUB\\AppData\\Local\\Temp\\evrptw_autolab_z2h1wmt2\\driver.py", line 26, in _call_solve\n    return solve(instance, **kwargs)\n  File "C:\\Users\\AYOUB\\AppData\\Local\\Temp\\evrptw_p15_u_8igrmu\\solver.py", line 20, in solve\n    routes[i].insert(state.route_index, available_station_ids[0])\n                     ^^^^^^^^^^^^^^^^^\nAtt'}
**Taxonomy:** {'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 3, 'GENERALITY': 0, 'FEASIBILITY': 1, 'OPTIMIZATION': 0, 'NO_OP': 0}
**Mechanism diversity (reporting):** {'algo_drafts': 1, 'charging_algo_drafts': 1, 'feasibility_families_seen': ['BATTERY'], 'committed_hash_count': 2, 'distinct_committed_hashes': 2}

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
  File "C:\Users\AYOUB\AppData\Local\Temp\evrptw_autolab_z2h1wmt2\driver.py", line 61, in <module>
    result = _call_solve()
  File "C:\Users\AYOUB\AppData\Local\Temp\evrptw_

**Committed hashes:** ['ccfeaedd9b890e08', '17e919438b710067']

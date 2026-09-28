# MINIMAL_COOPERATIVE_BUILD_V1

**Model:** `deepseek-coder:6.7b` | **run_id:** `seed55` | **llm_seed:** `55`
**Stopped:** CODING_FAILURE
**G4:** 0/4 | **PASS:** False
**Calls:** 9 | **tokens:** 17639/3318 | **wall:** 89.5s
**Roles invoked:** ['architect', 'critic', 'routing', 'search']
**Team incomplete orchestration:** False
**Primary failure:** {'failure_class': 'RUNTIME', 'role': 'search', 'gate': 'G1', 'detail': 'Traceback (most recent call last):\n  File "C:\\Users\\AYOUB\\AppData\\Local\\Temp\\evrptw_autolab_busdpzaq\\driver.py", line 61, in <module>\n    result = _call_solve()\n  File "C:\\Users\\AYOUB\\AppData\\Local\\Temp\\evrptw_autolab_busdpzaq\\driver.py", line 26, in _call_solve\n    return solve(instance, **kwargs)\n  File "C:\\Users\\AYOUB\\AppData\\Local\\Temp\\evrptw_p15_21p5hk6w\\solver.py", line 16, in solve\n    d = distance(instance.depot_id, cid)\n  File "C:\\Users\\AYOUB\\OneDrive - EMSI\\Bureau\\PHD_WORK\\LLM_Multi_Ag'}
**Taxonomy:** {'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 4, 'GENERALITY': 0, 'FEASIBILITY': 2, 'OPTIMIZATION': 0, 'NO_OP': 0}
**Mechanism diversity (reporting):** {'algo_drafts': 2, 'charging_algo_drafts': 0, 'feasibility_families_seen': ['DEPOT'], 'committed_hash_count': 2, 'distinct_committed_hashes': 2}

## Success levels

- **B0_executable:** True
- **B1_G1_G3:** False
- **B2_at_least_1_of_4_G4:** False
- **B3_G4_4_of_4:** False
- **B4_all_C5_ge_10_of_12:** False
- **Strong_B_12_of_12:** False

## Gates

- **G0:** PASS — contract_ok
- **G1:** FAIL — CODING_FAILURE:RUNTIME/search:Traceback (most recent call last):
  File "C:\Users\AYOUB\AppData\Local\Temp\evrptw_autolab_busdpzaq\driver.py", line 61, in <module>
    result = _call_solve()
  File "C:\Users\AYOUB\AppData\Local\Temp\evrptw_

**Committed hashes:** ['8ba6f0e84d120bf3', 'a45d06ae0739cd75']

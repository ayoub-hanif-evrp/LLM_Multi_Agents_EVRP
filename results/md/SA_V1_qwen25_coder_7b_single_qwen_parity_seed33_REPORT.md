# SINGLE_AGENT_MATCHED_V1 — `single_qwen_parity_seed33`

**Model:** `qwen2.5-coder:7b` | **seed:** `33` | **token budget:** `23579`

- highest_gate: `G4_partial_3`
- G4: `3/4` stopped=`PARTIAL_G4_3`
- calls=8 tokens=22051 (prompt=20498 completion=1553)
- wall_s=47.8 noop=4 hashes=3 final_hash=`1d87d9c8646280f2`
- primary: `{'failure_class': 'FEASIBILITY', 'role': 'single_coder', 'gate': 'G4', 'detail': 'WINDOW'}`
- taxonomy: `{'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 0, 'GENERALITY': 0, 'FEASIBILITY': 5, 'OPTIMIZATION': 0, 'NO_OP': 8}`
- families: `{'BATTERY': 1, 'WINDOW': 4}`

## Gates

- **G0**: passed=True detail=`contract_ok`
- **G1**: passed=True detail=`feasible`
- **G2**: passed=True detail=`feasible`
- **G3**: passed=True detail=`feasible`
- **G4**: passed=False detail=`PARTIAL 3/4 final={'c101C5': 'OK', 'c103C5': 'OK', 'r104C5': 'OK', 'r105C5': 'WINDOW'}`

# SINGLE_AGENT_MATCHED_V1 — `single_qwen_parity_seed55`

**Model:** `qwen2.5-coder:7b` | **seed:** `55` | **token budget:** `18207`

- highest_gate: `G4_partial_1`
- G4: `1/4` stopped=`TOKEN_BUDGET_PARTIAL_G4_1`
- calls=7 tokens=19383 (prompt=17888 completion=1495)
- wall_s=45.9 noop=3 hashes=3 final_hash=`2a3a18745a3a2ce1`
- primary: `{'failure_class': 'FEASIBILITY', 'role': 'single_coder', 'gate': 'G4', 'detail': 'WINDOW'}`
- taxonomy: `{'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 0, 'GENERALITY': 0, 'FEASIBILITY': 4, 'OPTIMIZATION': 0, 'NO_OP': 6}`
- families: `{'WINDOW': 4}`

## Gates

- **G0**: passed=True detail=`contract_ok`
- **G1**: passed=True detail=`feasible`
- **G2**: passed=True detail=`feasible`
- **G3**: passed=True detail=`feasible`
- **G4**: passed=False detail=`PARTIAL 1/4 final={'c101C5': 'OK', 'c103C5': 'WINDOW', 'r104C5': 'BATTERY', 'r105C5': 'BATTERY'}`

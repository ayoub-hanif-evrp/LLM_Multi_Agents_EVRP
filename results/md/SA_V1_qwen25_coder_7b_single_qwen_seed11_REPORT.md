# SINGLE_AGENT_MATCHED_V1 — `single_qwen_seed11`

**Model:** `qwen2.5-coder:7b` | **seed:** `11` | **token budget:** `18179`

- highest_gate: `G4_partial_2`
- G4: `2/4` stopped=`TOKEN_BUDGET_PARTIAL_G4_2`
- calls=9 tokens=19583 (prompt=17315 completion=2268)
- wall_s=69.7 noop=5 hashes=3 final_hash=`ae7376bed4b49c83`
- primary: `{'failure_class': 'FEASIBILITY', 'role': 'single_coder', 'gate': 'G4', 'detail': 'BATTERY'}`
- taxonomy: `{'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 0, 'GENERALITY': 0, 'FEASIBILITY': 6, 'OPTIMIZATION': 0, 'NO_OP': 10}`
- families: `{'BATTERY': 6}`

## Gates

- **G0**: passed=True detail=`contract_ok`
- **G1**: passed=True detail=`feasible`
- **G2**: passed=True detail=`feasible`
- **G3**: passed=True detail=`feasible`
- **G4**: passed=False detail=`PARTIAL 2/4 final={'c101C5': 'OK', 'c103C5': 'OK', 'r104C5': 'BATTERY', 'r105C5': 'BATTERY'}`

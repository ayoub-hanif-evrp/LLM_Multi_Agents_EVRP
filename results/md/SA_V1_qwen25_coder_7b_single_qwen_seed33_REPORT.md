# SINGLE_AGENT_MATCHED_V1 — `single_qwen_seed33`

**Model:** `qwen2.5-coder:7b` | **seed:** `33` | **token budget:** `23579`

- highest_gate: `G4_partial_2`
- G4: `2/4` stopped=`PARTIAL_G4_2`
- calls=11 tokens=24040 (prompt=21934 completion=2106)
- wall_s=62.5 noop=7 hashes=3 final_hash=`dfe78fde4b09db5f`
- primary: `{'failure_class': 'FEASIBILITY', 'role': 'single_coder', 'gate': 'G4', 'detail': 'BATTERY'}`
- taxonomy: `{'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 0, 'GENERALITY': 0, 'FEASIBILITY': 8, 'OPTIMIZATION': 0, 'NO_OP': 14}`
- families: `{'BATTERY': 8}`

## Gates

- **G0**: passed=True detail=`contract_ok`
- **G1**: passed=True detail=`feasible`
- **G2**: passed=True detail=`feasible`
- **G3**: passed=True detail=`feasible`
- **G4**: passed=False detail=`PARTIAL 2/4 final={'c101C5': 'OK', 'c103C5': 'OK', 'r104C5': 'BATTERY', 'r105C5': 'BATTERY'}`

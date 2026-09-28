# SINGLE_AGENT_MATCHED_V1 — `single_qwen_seed44`

**Model:** `qwen2.5-coder:7b` | **seed:** `44` | **token budget:** `6205`

- highest_gate: `G3`
- G4: `0/4` stopped=`TOKEN_BUDGET`
- calls=4 tokens=7572 (prompt=6815 completion=757)
- wall_s=24.3 noop=0 hashes=3 final_hash=`f775a3c6840ac497`
- primary: `{'failure_class': 'FEASIBILITY', 'role': 'single_coder', 'gate': 'G4', 'detail': 'WINDOW'}`
- taxonomy: `{'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 0, 'GENERALITY': 0, 'FEASIBILITY': 1, 'OPTIMIZATION': 0, 'NO_OP': 0}`
- families: `{'WINDOW': 1}`

## Gates

- **G0**: passed=True detail=`contract_ok`
- **G1**: passed=True detail=`feasible`
- **G2**: passed=True detail=`feasible`
- **G3**: passed=True detail=`feasible`
- **G4**: passed=False detail=`PARTIAL 0/4 final={'c101C5': 'WINDOW', 'c103C5': 'WINDOW', 'r104C5': 'WINDOW', 'r105C5': 'WINDOW'}`

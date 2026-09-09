# SINGLE_AGENT_MATCHED_V1 — `single_qwen_parity_seed44`

**Model:** `qwen2.5-coder:7b` | **seed:** `44` | **token budget:** `6205`

- highest_gate: `G1`
- G4: `0/4` stopped=`TOKEN_BUDGET`
- calls=3 tokens=6432 (prompt=5939 completion=493)
- wall_s=15.0 noop=0 hashes=2 final_hash=`467cedbe9075999b`
- primary: `{'failure_class': 'FEASIBILITY', 'role': 'single_coder', 'gate': 'G2', 'detail': 'BATTERY'}`
- taxonomy: `{'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 0, 'GENERALITY': 0, 'FEASIBILITY': 0, 'OPTIMIZATION': 0, 'NO_OP': 0}`
- families: `{}`

## Gates

- **G0**: passed=True detail=`contract_ok`
- **G1**: passed=True detail=`feasible`
- **G2**: passed=False detail=`BATTERY`
- **G3**: passed=None detail=``
- **G4**: passed=None detail=``

# SINGLE_AGENT_MATCHED_V1 — `single_qwen_seed55`

**Model:** `qwen2.5-coder:7b` | **seed:** `55` | **token budget:** `18207`

- highest_gate: `G1`
- G4: `0/4` stopped=`G2_FAIL`
- calls=7 tokens=14610 (prompt=13156 completion=1454)
- wall_s=43.3 noop=4 hashes=2 final_hash=`57d6ba3bb5e0ade5`
- primary: `{'failure_class': 'FEASIBILITY', 'role': 'single_coder', 'gate': 'G2', 'detail': 'BATTERY'}`
- taxonomy: `{'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 0, 'GENERALITY': 0, 'FEASIBILITY': 4, 'OPTIMIZATION': 0, 'NO_OP': 8}`
- families: `{'BATTERY': 4}`

## Gates

- **G0**: passed=True detail=`contract_ok`
- **G1**: passed=True detail=`feasible`
- **G2**: passed=False detail=`BATTERY`
- **G3**: passed=None detail=``
- **G4**: passed=None detail=``

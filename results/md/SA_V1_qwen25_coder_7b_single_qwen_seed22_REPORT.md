# SINGLE_AGENT_MATCHED_V1 — `single_qwen_seed22`

**Model:** `qwen2.5-coder:7b` | **seed:** `22` | **token budget:** `39157`

- highest_gate: `G1`
- G4: `0/4` stopped=`G2_FAIL`
- calls=7 tokens=15204 (prompt=13409 completion=1795)
- wall_s=50.4 noop=3 hashes=3 final_hash=`c10dc259239db095`
- primary: `{'failure_class': 'FEASIBILITY', 'role': 'single_coder', 'gate': 'G2', 'detail': 'BATTERY'}`
- taxonomy: `{'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 0, 'GENERALITY': 0, 'FEASIBILITY': 4, 'OPTIMIZATION': 0, 'NO_OP': 6}`
- families: `{'BATTERY': 4}`

## Gates

- **G0**: passed=True detail=`contract_ok`
- **G1**: passed=True detail=`feasible`
- **G2**: passed=False detail=`BATTERY`
- **G3**: passed=None detail=``
- **G4**: passed=None detail=``

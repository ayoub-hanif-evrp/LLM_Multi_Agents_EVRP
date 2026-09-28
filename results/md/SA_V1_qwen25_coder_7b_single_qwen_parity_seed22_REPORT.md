# SINGLE_AGENT_MATCHED_V1 — `single_qwen_parity_seed22`

**Model:** `qwen2.5-coder:7b` | **seed:** `22` | **token budget:** `39157`

- highest_gate: `G4_partial_2`
- G4: `2/4` stopped=`PARTIAL_G4_2`
- calls=11 tokens=30686 (prompt=28385 completion=2301)
- wall_s=68.0 noop=8 hashes=2 final_hash=`4470726f59edf942`
- primary: `{'failure_class': 'FEASIBILITY', 'role': 'single_coder', 'gate': 'G4', 'detail': 'BATTERY'}`
- taxonomy: `{'FORMAT': 0, 'SYNTAX': 0, 'RUNTIME': 0, 'GENERALITY': 0, 'FEASIBILITY': 8, 'OPTIMIZATION': 0, 'NO_OP': 16}`
- families: `{'BATTERY': 8}`

## Gates

- **G0**: passed=True detail=`contract_ok`
- **G1**: passed=True detail=`feasible`
- **G2**: passed=True detail=`feasible`
- **G3**: passed=True detail=`feasible`
- **G4**: passed=False detail=`PARTIAL 2/4 final={'c101C5': 'OK', 'c103C5': 'OK', 'r104C5': 'BATTERY', 'r105C5': 'BATTERY'}`

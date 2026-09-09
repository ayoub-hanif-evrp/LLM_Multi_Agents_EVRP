# MCB V1 — Cross-model empty-workspace screening

Protocol **frozen**. Same MCB V1 for every model. Optimization locked.

| Model | G0 | G1 | G2 | G3 | G4 | Highest capability | Stopped | Calls | Roles | Primary failure |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- |
| `deepseek-coder:6.7b` | ✓ | ✓ | ✗ | — | — | basic feasible routing | G2_FAIL | 12 | architect,charging,critic,routing,search | FEASIBILITY/BATTERY |
| `qwen2.5-coder:7b` | ✓ | ✓ | ✗ | — | — | basic feasible routing | CODING_FAILURE | 7 | architect,charging,critic,routing,search | GENERALITY/HARDCODED_INSTANCE_IDENTIFIER: ['S0'] |
| `codellama:7b` | ✓ | ✓ | ✗ | — | — | basic feasible routing | G2_FAIL | 11 | architect,charging,critic,routing | FEASIBILITY/VISIT |

## Notes

- DeepSeek `synth04` is the first accepted clean measurement (G2 BATTERY).
- Screening uses `run_id=screen01` for other models; do not cherry-pick reruns.
- Stronger anchors (DeepSeek-Coder-V2-Lite / Qwen3-Coder) require install + registry entry later.

## Contrast with Phase A repair

| Experiment | DeepSeek outcome |
| --- | --- |
| P1.3 repair of Qwen 3/4 seed | 4/4 → 12/12 C5 |
| MCB V1 empty-workspace synthesis | G0✓ G1✓ G2 BATTERY ✗ |

# FINAL experimental summary

## Experiments completed
- MCB V1 seeded synthesis: Qwen 7B / **Qwen 14B** / DeepSeek 6.7B / CodeLlama / V2-Lite × seeds 11–55
- SINGLE_AGENT_MATCHED_V1 **prompt-parity** re-runs (union domain guidance; soft token ceilings)
- P1.3 seeded repair (prior): 0/5 4/4 all models
- From-scratch G4=4/4 freeze + unchanged 12 C5
- Small optimization pilot (unlock instruction only)

## Main synthesis table (MCB V1)
| Model | G1 | G2 | G3 | reached G4 | G4 4/4 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Qwen 7B | 4/5 | 3/5 | 3/5 | 3/5 | 0/5 |
| **Qwen 14B** | **5/5** | 3/5 | 3/5 | 3/5 | **1/5** |
| DeepSeek 6.7B | 1/5 | 0/5 | 0/5 | 0/5 | 0/5 |
| CodeLlama 7B | 4/5 | 1/5 | 1/5 | 1/5 | 0/5 |
| DeepSeek-V2-Lite | 4/5 | 0/5 | 0/5 | 0/5 | 0/5 |

## Best from-scratch
- **Qwen2.5-Coder 14B seed33**: G4 **4/4**, hardcoded audit clean, **12/12 C5** unchanged
- Artifact: `results/md/artifacts/mcb_v1/FEASIBLE_SYNTHESIZED_SOLVER_V0_qwen14b_seed33/`
- Mechanism: per-customer route + general station insertion on battery failure (not `routes[0]`-only)
- Also: prompt-parity single-agent Qwen 7B seed11 independently reached **4/4 + 12/12**

## Five-agent vs single-agent (prompt parity)
| Metric | Five-agent Qwen 7B | Single-agent parity |
| --- | ---: | ---: |
| G2 / G3 / reached G4 | 3/5 | **4/5** |
| G4 4/4 | 0/5 | **1/5** |
| mean G4 | 1.6 | **2.0** |

**Outcome B.** Budget semantics: paired token-ceiling with call-boundary overshoot.

## Same-family capacity
7B → 14B produced the first MCB from-scratch **4/4**. G2/G3 reach stayed 3/5; mean G4 can fall when misses are 0/4. Capacity improves chance of full success, not every aggregate.

## Optimization pilot
Unlocked after 4/4. Unlock text only (no named metaheuristic).
- initial C5: 60 vehicles / 3617.06 distance (5/instance)
- final: **unchanged** (all 6 rounds runtime_fail on attempted edits)
- Report: `OPTIMIZATION_PILOT_REPORT.md`

## Scientific answers
### Q1 Executable synthesis from empty workspace?
**Yes.**

### Q2 Failure gates?
Early RUNTIME/G2 for weaker models; Qwen often reaches panel then BATTERY; 14B can clear full G4.

### Q3 Charging synthesis?
**Yes** (Qwen family).

### Q4 Schneider generalization?
**Yes for some runs:** 14B seed33 and SA parity seed11 → **12/12 C5**.

### Q5 Repair vs synthesis?
Seeded repair 0/15 4/4; historical unseeded DeepSeek repair succeeded once. Synthesis can now also reach 4/4.

### Q6 Five-agent vs single-agent?
With prompt parity: **single-agent matched or better** on these 5 seeds (Outcome B).

### Q7 Stronger model?
V2-Lite no; **same-family 14B yes** (first 4/4).

### Q8 Dominant failures?
RUNTIME early; BATTERY at panel; opt pilot runtime on merge attempts.

### Q9 From-scratch 4/4 generalization?
**Yes — 12/12 C5** (both frozen solvers), no hardcoded IDs.

### Q10 Optimization without supplied metaheuristic?
**Attempted; no fleet/distance improvement** in this small pilot (edits broke runtime).

## Remaining gaps before submission
1. Optionally expand Qwen 7B five-agent vs single-agent to ~10 paired seeds (Outcome B still n=5).
2. Optionally expand Qwen 14B to 10 seeds for a stabler 4/4 rate.
3. Stronger optimization pilot design (still no algorithmic hints) if pursuing an optimization contribution.
4. Stop architecture churn; write the capability paper.

# MCB V1 — Qwen2.5-Coder 14B same-family capacity anchor

Frozen MCB V1. Seeds `11/22/33/44/55`. Compares `qwen2.5-coder:14b` vs `7b`.

| Model | n | G1 | G2 | G3 | reached G4 | G4 4/4 | mean G4 | median calls |
| --- | -: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `qwen2.5-coder:14b` | 5 | 5/5 | 3/5 | 3/5 | 3/5 | 1/5 | 0.8 | 11 |
| `qwen2.5-coder:7b` | 5 | 4/5 | 3/5 | 3/5 | 3/5 | 0/5 | 1.6 | 11 |

## Per-seed (14B)

- seed `11`: G1=True G2=True G3=True G4=False progress=0/4 calls=19 stopped=G4_FAIL primary=FEASIBILITY/BATTERY
- seed `22`: G1=True G2=False G3=False G4=False progress=0/4 calls=11 stopped=G2_FAIL primary=FEASIBILITY/BATTERY
- seed `33`: G1=True G2=True G3=True G4=True progress=4/4 calls=3 stopped=SUCCESS primary=None/
- seed `44`: G1=True G2=True G3=True G4=False progress=0/4 calls=18 stopped=G4_FAIL primary=FEASIBILITY/BATTERY
- seed `55`: G1=True G2=False G3=False G4=False progress=0/4 calls=11 stopped=G2_FAIL primary=FEASIBILITY/BATTERY

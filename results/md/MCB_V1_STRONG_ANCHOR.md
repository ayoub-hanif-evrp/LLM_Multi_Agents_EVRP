# MCB V1 — Strong-model anchor (seeded)

MCB V1 **frozen**. Same seeds `11/22/33/44/55` as the ~7B package.

**Hardware note:** Preferred anchor `qwen3-coder:30b` (~19GB Q4) deferred on this machine
(RTX A2000 12GB + ~16GB system RAM). Running **`deepseek-coder-v2:16b`**
(DeepSeek-Coder-V2-Lite-Instruct, ~8.9GB, MoE ~2.4B active) instead.

| Model | n | G1 | G2 | G3 | G4 4/4 | Reached real G4 | Median calls | Main failure |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `deepseek-coder-v2:16b` | 5 | 4/5 | 0/5 | 0/5 | 0/5 | 0/5 | 5 | RUNTIME |
| `qwen2.5-coder:7b` | 5 | 4/5 | 3/5 | 3/5 | 0/5 | 3/5 | 11 | FEASIBILITY/BATTERY |
| `deepseek-coder:6.7b` | 5 | 1/5 | 0/5 | 0/5 | 0/5 | 0/5 | 9 | RUNTIME |
| `codellama:7b` | 5 | 4/5 | 1/5 | 1/5 | 0/5 | 1/5 | 6 | RUNTIME |

## Per-seed detail (strong anchor)

- seed `11`: G1=True G2=False G3=False G4=False g4_progress=0/4 calls=5 stopped=CODING_FAILURE primary=GENERALITY/HARDCODED_INSTANCE_IDENTIFIER: ['S0']
- seed `22`: G1=True G2=False G3=False G4=False g4_progress=0/4 calls=11 stopped=G2_FAIL primary=FEASIBILITY/DEPOT
- seed `33`: G1=True G2=False G3=False G4=False g4_progress=0/4 calls=10 stopped=CODING_FAILURE primary=RUNTIME/Traceback (most recent call last):
- seed `44`: G1=True G2=False G3=False G4=False g4_progress=0/4 calls=5 stopped=CODING_FAILURE primary=RUNTIME/Traceback (most recent call last):
- seed `55`: G1=False G2=False G3=False G4=False g4_progress=0/4 calls=4 stopped=CODING_FAILURE primary=RUNTIME/Traceback (most recent call last):

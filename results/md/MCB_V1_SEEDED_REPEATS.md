# MCB V1 — Seeded empty-workspace repeats

MCB V1 **frozen**. Experimental factor: Ollama `seed` only.
Seeds: `11, 22, 33, 44, 55`. Preliminary `screen01`/`synth04` excluded.

| Model | n | G1 success | G2 success | G3 success | G4 success | Median calls | Main failure |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `deepseek-coder:6.7b` | 5 | 1/5 | 0/5 | 0/5 | 0/5 | 9 | RUNTIME |
| `qwen2.5-coder:7b` | 5 | 4/5 | 3/5 | 3/5 | 0/5 | 11 | FEASIBILITY/BATTERY |
| `codellama:7b` | 5 | 4/5 | 1/5 | 1/5 | 0/5 | 6 | RUNTIME |

## Per-seed detail

### `deepseek-coder:6.7b`

- seed `11`: G1=False G2=False G3=False G4=False calls=4 stopped=CODING_FAILURE primary=RUNTIME/Traceback (most recent call last):
- seed `22`: G1=True G2=False G3=False G4=False calls=11 stopped=G2_FAIL primary=FEASIBILITY/BATTERY
- seed `33`: G1=False G2=False G3=False G4=False calls=10 stopped=G1_FAIL primary=FEASIBILITY/VISIT
- seed `44`: G1=False G2=False G3=False G4=False calls=4 stopped=CODING_FAILURE primary=RUNTIME/timeout
- seed `55`: G1=False G2=False G3=False G4=False calls=9 stopped=CODING_FAILURE primary=RUNTIME/Traceback (most recent call last):

### `qwen2.5-coder:7b`

- seed `11`: G1=True G2=True G3=True G4=False calls=11 stopped=PARTIAL_G4_3 primary=FEASIBILITY/BATTERY
- seed `22`: G1=True G2=True G3=True G4=False calls=21 stopped=PARTIAL_G4_2 primary=FEASIBILITY/BATTERY
- seed `33`: G1=True G2=True G3=True G4=False calls=13 stopped=PARTIAL_G4_3 primary=FEASIBILITY/BATTERY
- seed `44`: G1=False G2=False G3=False G4=False calls=4 stopped=CODING_FAILURE primary=RUNTIME/timeout
- seed `55`: G1=True G2=False G3=False G4=False calls=11 stopped=G2_FAIL primary=FEASIBILITY/BATTERY

### `codellama:7b`

- seed `11`: G1=True G2=False G3=False G4=False calls=7 stopped=CODING_FAILURE primary=RUNTIME/Traceback (most recent call last):
- seed `22`: G1=False G2=False G3=False G4=False calls=2 stopped=CODING_FAILURE primary=FORMAT/missing def solve
- seed `33`: G1=True G2=True G3=True G4=False calls=35 stopped=G4_FAIL primary=FEASIBILITY/BATTERY
- seed `44`: G1=True G2=False G3=False G4=False calls=5 stopped=CODING_FAILURE primary=GENERALITY/HARDCODED_INSTANCE_IDENTIFIER: ['S0']
- seed `55`: G1=True G2=False G3=False G4=False calls=6 stopped=CODING_FAILURE primary=RUNTIME/Traceback (most recent call last):

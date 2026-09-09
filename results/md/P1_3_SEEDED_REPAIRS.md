# Seeded P1.3 repair repeats

Frozen P1.3 protocol. Common 3/4 seed. Seeds `11/22/33/44/55`.

| Model | n | 4/4 successes | Success rate | Median calls to success | Regressions | NO_OP rate |
| --- | -: | ---: | ---: | ---: | ---: | ---: |
| Qwen 7B | 5 | 0 | 0/5 | None | 0 | 4/5 |
| DeepSeek 6.7B | 5 | 0 | 0/5 | None | 0 | 0/5 |
| CodeLlama 7B | 5 | 0 | 0/5 | None | 0 | 4/5 |

## Per-seed

### Qwen 7B

- seed `11`: 4/4=False g4=3/4 calls=6 stopped=PARTIAL_G4_3_NO_PROGRESS c5=None/None regressions=0
- seed `22`: 4/4=False g4=3/4 calls=4 stopped=PARTIAL_G4_3 c5=None/None regressions=0
- seed `33`: 4/4=False g4=3/4 calls=4 stopped=PARTIAL_G4_3 c5=None/None regressions=0
- seed `44`: 4/4=False g4=3/4 calls=4 stopped=PARTIAL_G4_3 c5=None/None regressions=0
- seed `55`: 4/4=False g4=3/4 calls=16 stopped=PARTIAL_G4_3_BUDGET c5=None/None regressions=0

### DeepSeek 6.7B

- seed `11`: 4/4=False g4=3/4 calls=16 stopped=PARTIAL_G4_3_BUDGET c5=None/None regressions=0
- seed `22`: 4/4=False g4=3/4 calls=16 stopped=PARTIAL_G4_3_BUDGET c5=None/None regressions=0
- seed `33`: 4/4=False g4=3/4 calls=16 stopped=PARTIAL_G4_3_BUDGET c5=None/None regressions=0
- seed `44`: 4/4=False g4=3/4 calls=16 stopped=PARTIAL_G4_3_BUDGET c5=None/None regressions=0
- seed `55`: 4/4=False g4=3/4 calls=16 stopped=PARTIAL_G4_3_BUDGET c5=None/None regressions=0

### CodeLlama 7B

- seed `11`: 4/4=False g4=3/4 calls=6 stopped=PARTIAL_G4_3_NO_PROGRESS c5=None/None regressions=0
- seed `22`: 4/4=False g4=3/4 calls=6 stopped=PARTIAL_G4_3_NO_PROGRESS c5=None/None regressions=0
- seed `33`: 4/4=False g4=3/4 calls=6 stopped=PARTIAL_G4_3_NO_PROGRESS c5=None/None regressions=0
- seed `44`: 4/4=False g4=3/4 calls=16 stopped=PARTIAL_G4_3_BUDGET c5=None/None regressions=0
- seed `55`: 4/4=False g4=3/4 calls=6 stopped=PARTIAL_G4_3_NO_PROGRESS c5=None/None regressions=0


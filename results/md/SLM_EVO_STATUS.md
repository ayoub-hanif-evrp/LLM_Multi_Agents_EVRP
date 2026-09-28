# SLM-Evo optimization campaign status

## Frozen artifacts (immutable unless noted)
| Tag | Vehicles | Notes |
| --- | ---: | --- |
| `OPT_V1` | **53** | First win; never overwrite |
| `OPT_V2_09ee68b15c8d2906` | **30** | Best from OPT_V1 5-seed campaign (seed 22) |

## OPT_V1 → 5-seed robust C5 (done)
Parent OPT_V1 (53). Gate: all-12 C5 feasible. **5/5** seeds improved with 12/12.

| Seed | Trajectory | Freeze |
| ---: | --- | --- |
| 11 | 53 → 50 | `OPT_SEED11_11b66eed154c9abb` |
| **22** | **53 → 50 → 30** | `OPT_SEED22_09ee68b15c8d2906` → **OPT_V2** |
| 33 | 53 → 50 | `OPT_SEED33_3c90183237551607` |
| 44 | 53 → 50 | `OPT_SEED44_112b2890d54f226c` |
| 55 | 53 → 50 | `OPT_SEED55_419b2f7f69785d8a` |

Report: `SLM_EVO_OPT_V1_5SEED_REPORT.md`

## Next (not started)
Scale-aware evolution: fixed C10/C15 development subset in selection pressure, then held-out larger Schneider eval.

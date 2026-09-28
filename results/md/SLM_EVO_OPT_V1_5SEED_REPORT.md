# SLM-Evo — SLM_EVO_OPT_V1_5SEED_REPORT

**Parent:** OPT_V1 (53 veh / 12/12 C5)
**Profile:** `qwen25_coder_14b` | **timestamp:** `2026-09-10T23:38:29.112263+00:00`
**Protocol:** full budget, `stop_on_milestone=False`, all-C5 12/12 gate, seeds `[11, 22, 33, 44, 55]`

| Seed | Trajectory (all-C5 veh) | Final veh | Δ | First improve gen | 12/12? | Freeze | Mechanisms |
| ---: | --- | ---: | ---: | ---: | --- | --- | --- |
| 11 | `53 -> 50` | 50 | -3 | 3 | 12/12 | `OPT_SEED11_11b66eed154c9abb` | g3/critic_inventor/REPLACE:solve |
| 22 | `53 -> 50 -> 30` | 30 | -23 | 5 | 12/12 | `OPT_SEED22_09ee68b15c8d2906` | g5/charging/REPLACE:solve; g6/architect/ADD:evaluate_route_with_charging+REPLACE:merge_routes_with_charging_stations+REPLACE:evaluate_route_with_charging |
| 33 | `53 -> 50` | 50 | -3 | 2 | 12/12 | `OPT_SEED33_3c90183237551607` | g2/architect/REPLACE:solve |
| 44 | `53 -> 50` | 50 | -3 | 0 | 12/12 | `OPT_SEED44_112b2890d54f226c` | g0/critic_inventor/REPLACE:solve |
| 55 | `53 -> 50` | 50 | -3 | 0 | 12/12 | `OPT_SEED55_419b2f7f69785d8a` | g0/charging/REPLACE:solve |

**Valid seeds with fleet reduction (12/12):** `5/5`

**Baseline parent vehicles:** `53`

Verdict: **reproducible feasible improvement** below parent fleet → freeze best and proceed to scale-aware evolution later.

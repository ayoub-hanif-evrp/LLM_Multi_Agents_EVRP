# SLM-Evo optimization reproducibility (5 seeds)

**Parent:** synthesized Qwen14B seed33 (all-12 C5 **60** vehicles)
**Profile:** `qwen25_coder_14b` | **timestamp:** `2026-09-09T22:55:48.482500+00:00`
**Protocol:** full budget, `stop_on_milestone=False`, seeds `[11, 22, 33, 44, 55]`

| Seed | Trajectory (all-C5 veh) | Final veh | Δ | First improve gen | 12/12? | Mechanisms |
| ---: | --- | ---: | ---: | ---: | --- | --- |
| 11 | `60 -> 57 -> 55 -> 55` | 55 | -5 | 0 | 12/12 | g0/critic_inventor/ADD:is_battery_feasible+ADD:insert_charging_station+REPLACE:solve; g2/routing/REPLACE:solve; g4/charging/REPLACE:solve |
| 22 | `60` | 60 | 0 | — | 12/12 | — |
| 33 | `60 -> 57 -> 55` | 55 | -5 | 7 | 12/12 | g7/search/ADD:is_battery_feasible+ADD:insert_charging_station+REPLACE:solve; g16/routing/REPLACE:solve+ADD:merge_routes |
| 44 | `60 -> 39` | 39 | -21 | 6 | 10/12 | g6/critic_inventor/ADD:calculate_total_distance+REPLACE:solve |
| 55 | `60` | 60 | 0 | — | 12/12 | — |

**Seeds with feasible fleet reduction (12/12):** `2/5` (11 and 33 → **55** vehicles).  
**Seed 44** reached panel win / trajectory `60 -> 39` but final all-C5 is only **10/12** — not counted as a valid freeze.

Verdict: **reproducible feasible fleet improvement** → continue from best seed winner **seed 11** (`afb7fe377add7ebb`, 55 veh, lower distance than seed 33).

# Research results

Status: `LLM_POLICY_BEHAVIOR_CHANGED`.

The two-route routing expression selects the cheaper vehicle on the four-node repair. That is not a discovery result: there is no confirmation set, and `marginal_removal_distance` is `NOT_GENERALIZED`.

The one-route Qwen run is kept in `results/recovery_v4/live.json`. The two-route gate is `results/recovery_v4/gate1_two_route.json`. Confirmation and Schneider RC2 were not run.

Model, when called: `qwen3-coder:30b`, digest `sha256-1194192cf2a187eb02722edcc3f77b11d21f537048ce04b67ccf8ba78863006a`. Schema `2026-10-24.v4`.

## One-route live run, three model calls, 708 tokens

Reinserting customer `C` into `D-A-B-D`. Classical repair produces `D-A-B-C-D`, one vehicle, distance 24. The hand-written sign flip `0.0 - delta_distance` produces `D-A-C-B-D`, distance 30.4339811320566. Both are feasible. `delta_distance + 0.01 * due_time` selects the same position as `delta_distance`.

| Arm | Expression | Repair route | Feasible | Distance | Changed the position |
| --- | --- | --- | --- | --- | --- |
| Classical objective | historical repair | `D-A-B-C-D` | yes | 24 | baseline |
| Random grammar | `route_load_slack_after_insertion + 5.0 * delta_travel_time` | `D-A-B-C-D` | yes | 24 | no |
| Single designer | `delta_distance + 0.1 * route_load_slack_after_insertion - 0.05 * route_customer_count + new_vehicle_fixed_cost` | `D-A-B-C-D` | yes | 24 | no |
| Architect plus routing | `delta_distance + 0.1 * route_load_slack_after_insertion` | `D-A-B-C-D` | yes | 24 | no |

On that one route, load slack, customer count, and new-vehicle cost do not vary. The critic was not called. No objective improvement was measured.

## Two-route gate, zero model calls

Hiermann micro `two_route_cost`. An ICE route through `(2, 2)` and a BEV route through `(-20, 0)`. Insert customer `C` at `(2, 0)`. Fixed costs are already sunk. The fossil price and the electricity price are both 1.

| Policy | Vehicle for C | Feasible | Native cost | Differs from the objective-best position |
| --- | --- | --- | --- | --- |
| `delta_distance` | ICE | yes | 72.2842712474619 | yes |
| `incremental_energy_cost` | BEV | yes | 60.9685424949238 | no |

Incremental energy cost is 11.715728752538098 on the ICE and 0.40000000000000036 on the BEV. The longer detour is the cheaper feasible repair. A generated expression that selects the ICE is the same decision as `delta_distance` and is not counted as a behavior change.

## Two-route live run, four model calls, 1052 tokens

Command: `uv run voltforge experiments policy-recovery-v4 --live`. File: `results/recovery_v4/live_two_route.json`. The one-route file was left in place. The critic was not called, because the routing expression changed the vehicle and lowered the native cost. Confirmation was not run.

| Arm | Expression | Vehicle for C | Feasible | Native cost | Changed from `delta_distance` |
| --- | --- | --- | --- | --- | --- |
| `delta_distance` | distance only | ICE | yes | 72.2842712474619 | baseline |
| Random grammar | `route_load_slack_after_insertion + 5.0 * delta_travel_time` | ICE | yes | 72.2842712474619 | no |
| Single designer | `delta_distance + 0.1 * incremental_energy_cost - 0.01 * route_load_slack_after_insertion` | ICE | yes | 72.2842712474619 | no |
| Architect plus routing | `incremental_energy_cost + 0.5 * delta_distance - 0.3 * route_load_slack_after_insertion` | BEV | yes | 60.9685424949238 | yes |

The architect text did not name a schema feature, so it was not passed on as a grounded hypothesis. The routing expression still matches the energy-cost repair on this micro. The single-agent and random expressions do not. This does not establish a multi-agent advantage.

## Removal transfer

Label: `NOT_GENERALIZED`. The expression was not edited after the losses.

`own_route_distance` stays unpromoted. `marginal_removal_distance` was judged once against `policy=None` on Hiermann `c101_21`, `r101_21`, and `c201_21`, seeds 7, 11, and 22, 15 seconds and 40 ALNS iterations, zero model calls. Repair ranking stayed on the historical objective. The file is `results/recovery_v4/marginal_removal.json`.

| Instance | Seed | Classical cost | Marginal-removal cost | Vehicles |
| --- | --- | --- | --- | --- |
| c101_21 | 7 | 4150.872544094683 | 4067.646030564055 | 20, 20 |
| c101_21 | 11 | 4164.778526628387 | 3913.1773808060316 | 20, 19 |
| c101_21 | 22 | 4154.5545883236555 | 4050.031830929426 | 20, 20 |
| r101_21 | 7 | 4032.9674353081436 | 4020.242642478671 | 18, 18 |
| r101_21 | 11 | 4047.7217930331963 | 4057.05075136774 | 18, 18 |
| r101_21 | 22 | 4045.143882316208 | 4047.4831171244487 | 18, 18 |
| c201_21 | 7 | 1226.9918847018703 | 1210.8323469426368 | 6, 6 |
| c201_21 | 11 | 1260.5414677174158 | 1220.8810099615569 | 6, 6 |
| c201_21 | 22 | 1246.15779373392 | 1180.7230249358508 | 6, 6 |

Every row is feasible and finished inside the time limit. The two `r101_21` losses block promotion.

## Classical fleet repair

Zero model calls. When no open route can take the customer, construction now prices a larger vehicle against opening another small one, and a feasible insertion is chosen by energy cost across vehicle types. File: `results/recovery_v4/native_energy_repair.json`. Decision: `mixed`. This is a classical change, not a model result.

| Instance | Seed | Previous classical | Native-cost repair | Vehicles |
| --- | --- | --- | --- | --- |
| c101_21 | 7 | 4150.872544094683 | 3199.26388161663 | 20 to 13 |
| c101_21 | 11 | 4164.778526628387 | 3181.763873410584 | 20 to 13 |
| c101_21 | 22 | 4154.5545883236555 | 3129.97724274773 | 20 to 13 |
| r101_21 | 7 | 4032.9674353081436 | 4060.3916494079685 | 18 to 18 |
| r101_21 | 11 | 4047.7217930331963 | 4067.8703051713737 | 18 to 18 |
| r101_21 | 22 | 4045.143882316208 | 4062.7870913094894 | 18 to 18 |
| c201_21 | 7 | 1226.9918847018703 | 1162.4406210789816 | 6 to 5 |
| c201_21 | 11 | 1260.5414677174158 | 1199.6440839880534 | 6 to 5 |
| c201_21 | 22 | 1246.15779373392 | 1185.6709844794495 | 6 to 5 |

All nine repairs are feasible and inside the 15 second budget. `c101_21` and `c201_21` improve. `r101_21` is worse on every seed.

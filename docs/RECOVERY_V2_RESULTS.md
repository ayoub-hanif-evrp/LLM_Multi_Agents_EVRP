# Recovery v2 results

Baseline: `dd5949d0a5a7f679f3ba14a411539a23110c0d0a`.

Branch: `recovery/policy-dd5949d`.

Command: `uv run voltforge experiments policy-recovery --live`

Model: `qwen3-coder:30b`, digest `sha256-1194192cf2a187eb02722edcc3f77b11d21f537048ce04b67ccf8ba78863006a`.

The full regression suite passed: 259 tests. Gate 1 also passed with zero model calls. The default insertion policy does not change its own probe decision. The controlled expression `0.0 - delta_distance` changes the probe's selected move and the moves recorded by `solve_classical` on Schneider c101C5.

## What the live proof ran

Three model calls, 621 tokens, 24.086 seconds of wall time. The critic was not called: the runner skipped it after the routing expression changed the synthetic probe. No confirmation seeds and no 426-instance run were started. The solver budget on c101C5 was seed 1, 2 seconds, and 8 ALNS iterations.

The raw runner file `results/recovery_v2/live_proof.json` stores status `LLM_POLICY_GENERATED` because the routing expression changed the synthetic probe. That label is not the verdict. On the instance, the recorded moves did not change.

| System | Expression | Probe selected move | c101C5 moves vs default | Feasible | Native objective | Model calls |
| --- | --- | --- | --- | --- | --- | --- |
| Classical default | frozen insertion formula | unchanged | baseline | yes | 2 vehicles, distance 267.3289940850671 | 0 |
| Random grammar, as executed | `ready_time + 5.0 * due_time` without a function wrapper | did not load | not solved in the live file |  |  | 0 |
| Random grammar, wrapped recheck | same string wrapped, zero extra model calls | changed | identical | yes | 2 vehicles, distance 267.3289940850671 | 0 |
| Single designer | `delta_distance + 0.1 * max(0, ready_time - due_time) + 0.01 * demand` | ranking changed, selected probe move unchanged | identical | yes | 2 vehicles, distance 267.3289940850671 | included in the 3 |
| Architect plus routing specialist | `delta_distance + 0.01 * due_time` | changed | identical | yes | 2 vehicles, distance 267.3289940850671 | included in the 3 |

The architect hypothesis was accepted as grounded because it names `delta_distance` and travel distance. It does not identify a measurable insertion change beyond "use delta distance." Charging and search specialists were not required by that hypothesis and did not run.

## Hiermann route-length removal

Zero model calls. The removal feature `own_route_distance` is the travel distance of the route that contains the customer. The historical `route_distance_share` value is unchanged, so the default policy still matches the frozen classical call. The expression `own_route_distance` was written by hand. It is not an LLM policy.

Budget: 15 seconds, 40 ALNS iterations, the classical pilot budget. Lower total cost is better. Vehicle counts did not change.

| Instance | Seed | Classical cost | Long-route removal | Result |
| --- | ---: | ---: | ---: | --- |
| c101_21 | 7 | 4150.872544094683 | 4089.8333047771343 | win |
| c101_21 | 11 | 4164.778526628387 | 4164.45627408774 | win |
| c101_21 | 22 | 4154.5545883236555 | 4081.2731649230145 | win |
| r101_21 | 7 | 4032.9674353081436 | 4020.242642478671 | win |
| r101_21 | 11 | 4047.7217930331963 | 4057.05075136774 | loss |
| r101_21 | 22 | 4045.143882316208 | 4047.4831171244487 | loss |
| c201_21 | 7 | 1226.9918847018703 | 1234.641906684666 | loss |
| c201_21 | 11 | 1260.5414677174158 | 1271.531594380405 | loss |
| c201_21 | 22 | 1246.15779373392 | 1234.032246161524 | win |

`delta_distance + new_route_fixed_cost` tied the classical cost on c101_21 seed 7 and was not carried forward. The long-route rule is not promoted: it loses on r101_21 and c201_21.

## Verdict

`POLICY_INTERFACE_VALIDATED`

The classical interface can change a real selected move, as the deterministic flip shows. The three live calls produced valid insertion code, and both evaluated model policies preserved feasibility, but neither changed a recorded c101C5 decision or the native objective. The wrapped random control tied the same objective. That is not an optimization improvement, and it is not a confirmed comparison across seeds. Gate 3 was not opened.

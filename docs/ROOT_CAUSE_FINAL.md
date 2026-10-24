# Root causes verified on the repair micro

Commit under test: `cba6161` plus the uncommitted v4 repair changes. The micro is depot `D` and customers `A (5,0)`, `B (6,0)`, `C (0,8)`.

## Same ranking from a due-time term

`delta_distance + 0.01 * due_time` is the expression the live Qwen run returned. On the three real insertion positions for `C`, `due_time` is 100 at every position and `delta_distance` is not. The argmin matches `delta_distance`. That is `tests/test_real_policy_decisions.py`.

## ALNS repair ignored the scorer

`repair_greedy` in `backbone/alns.py` ranked a non-heterogeneous insertion by `_acceptance_score`, which is the native objective. A loaded v1 bundle therefore recorded `insertion_score` call count 0 while reinserting `C`.

## What v4 changes

Schema `2026-10-24.v4` is opt-in. `policy is None` and every v1, v2, and v3 bundle still use the historical objective ranking. A v4 insertion scorer ranks only the candidates that already passed the capacity, depot, precedence, and time-window screen. The incumbent rule in `alns_improve` is unchanged.

The features that are actually computed are `delta_distance`, `delta_travel_time`, `route_load_slack_after_insertion` from the candidate vehicle, `route_customer_count`, `new_vehicle_fixed_cost`, `incremental_energy_cost`, and `battery_margin`. Removal adds `marginal_removal_distance` for the whole pickup-delivery unit when the stops share a route. `route_distance_share` remains the historical constant for v1.

On the one-route micro, `0.0 - delta_distance` inserts `C` at a different index from the classical repair, both results stay feasible, and the trace flag `changed_from_objective` is true. Customer `A` lies on the segment `D-B`, so its marginal removal distance is 0 while `B` is positive. Load slack, customer count, and fixed cost do not vary on that one route, so an expression that keeps a positive distance weight cannot leave the classical position.

The two-route case is the one where the native objective and the shortest detour disagree. Depot `D`, ICE route through `A (2,2)`, BEV route through `B (-20,0)`, insert `C (2,0)`. The ICE detour is shorter and has the higher incremental fuel cost. `delta_distance` places `C` on the ICE. `incremental_energy_cost` places `C` on the BEV, matches the objective-best screened candidate, and has the lower native cost. Both repairs stay feasible. A hybrid energy cost is not computed and returns 0.

Goeke pair repair uses the same v4 scorer on pickup-then-delivery edits. `battery_margin` is the minimum arrival state of charge from `simulate_route`. It is not a station detour and it is not a nonlinear charging price.

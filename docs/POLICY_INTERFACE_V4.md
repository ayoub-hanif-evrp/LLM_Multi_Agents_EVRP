# Policy interface v4

Schema id: `2026-10-24.v4`.

## Who it applies to

| Family | v4 insertion repair | Why |
| --- | --- | --- |
| Schneider | supported | Non-heterogeneous ALNS repair ranks screened positions with `insertion_score`. |
| Goeke | supported for pair repair | A v4 bundle ranks pickup-then-delivery edits with `edited_route_features`. A non-v4 bundle still uses the native objective. |
| Montoya, Bezzi | insertion features only | `battery_margin` is the minimum arrival state of charge from `simulate_route` on the trial route. Station choice and nonlinear partial charging stay on the existing operators. No charging cost is invented. |
| Hiermann | supported | A v4 bundle ranks screened insertions with `_repair_one_v4`, including a heterogeneous fleet. A non-v4 bundle still uses `insert_customer_fast`. |

A bundle with any other schema does not enter `_repair_one_v4` or `_repair_pair_v4`.

## Insertion features

| Name | Unit | How it is computed |
| --- | --- | --- |
| `delta_distance` | distance | Added length of the two new arcs minus the skipped arc. Uses the published matrix when the instance has one. |
| `delta_travel_time` | time | Same arcs through `travel_time` and the candidate vehicle. |
| `route_load_slack_after_insertion` | demand | Candidate vehicle capacity minus the route load after the customer is added. |
| `route_customer_count` | count | Customers already on that route. |
| `new_vehicle_fixed_cost` | money | The candidate vehicle's fixed cost when the route has no customer yet, otherwise 0. |
| `incremental_energy_cost` | money | Pure ICE: distance delta times `fuel_consumption_rate` times the fossil price. Pure EV: energy of the two new arcs minus the skipped arc, times the electricity price. A hybrid vehicle returns 0 because that mix is not computed. |
| `battery_margin` | energy | Minimum `battery_arrival` from `simulate_route` on the trial route. A pure ICE returns 0. A simulation error returns -1. |

`due_time`, `ready_time`, and `demand` are omitted because they do not change across positions of one customer.

## Removal features

| Name | Unit | How it is computed |
| --- | --- | --- |
| `due_time` | time | Mean finite due time of the removal unit. |
| `marginal_removal_distance` | distance | Route length minus the length after every stop in the unit is deleted. |
| `time_window_width` | time | Finite due time minus ready time, averaged over the unit. |
| `rng_value` | unitless | One draw in `[0, 1)`. |

## Feasibility

The scorer does not accept or reject a route. A candidate that fails the hard screen is not scored. The trace keeps at most 64 repair events, with the selected position, the objective-best position, and whether they differ. `alns_improve` still keeps the best feasible incumbent.

On the two-route Hiermann micro, `delta_distance` and `incremental_energy_cost` select different vehicles. A generated expression whose selected vehicle matches `delta_distance` is recorded as unchanged and is not treated as a discovery.

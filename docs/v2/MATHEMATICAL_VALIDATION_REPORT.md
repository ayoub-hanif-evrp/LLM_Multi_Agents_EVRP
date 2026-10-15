# Mathematical validation report

This report records the formulations the v2 evaluator implements, where each formula comes from, and what was checked numerically. It does not claim that every published optimum has been reproduced, and it does not treat a passing unit test as a completed benchmark campaign.

## Schneider EVRPTW

Source: Schneider, Stenger, Goeke (2014), as implemented by the frozen legacy evaluator in `problem/evaluator.py`.

- Distance: Euclidean.
- Travel time: distance / velocity.
- Recharge: full recharge only. Duration = energy deficit × inverse recharging rate.
- Time windows: waiting allowed; service must start by the due date. Depot return is checked against the depot due date.
- Objective key: `(vehicles, total distance)`, minimized lexicographically. The legacy scalar distance is unchanged.

The v2 adapter matches the legacy distance on the one-customer micro instance. The legacy evaluator was not modified.

## Montoya E-VRP-NL

Source: Montoya et al. (2017) instance readme and piecewise charging breakpoints stored in the XML.

Units: energy in Wh, distance in km, speed in km/h, charging breakpoints as `(battery level, cumulative time)`.

- Travel time = distance / speed.
- Energy = distance × consumption rate.
- Charging time between SoC `a` and `b` is the difference of the piecewise-linear interpolant. The curve is required to be monotone.
- A stop may set `target_soc` or `charge_amount`. There is no implicit full recharge when a target is set.
- Objective key: `(total route duration,)`, including travel, service, and charging time.
- Maximum route duration is a hard constraint when the instance provides it.

Checked: on `tc0c10s2cf1`, charging from empty to 60%, 80%, and 100% of the published curve is strictly increasing in time. A route that arrives at 50% SoC and then targets those three levels has three different total durations.

## Bezzi & Ceselli EVRP-MRT (GVRP-MTPR)

Sources:

- Felipe, Ortuño, Righini, Tirado (2014), Green VRP with multiple technologies and partial recharges.
- Ceselli, Felipe, Ortuño, Righini, Tirado (2021), *Operations Research Forum*: minimize recharge cost, not distance.

```
cost = Σ (f + γ_h · δ_h)   over every positive recharge, including the depot
time = Σ travel_time + Σ service_time + Σ ρ_h · δ_h   ≤ max_travel_time
```

- `γ_h` is the unit energy cost of technology `h`. `ρ_h` is time per unit energy.
- Technology 0 is the depot technology (`ρ_0 = 0` in these files).
- Stations list every `<has_tech>` child. A recharge uses one of those technologies.
- Symmetric `<links>` are stored in both directions. Travel time and energy stay separate matrices. Distance is not substituted for time.
- Charge amounts are not in the solution XML. For a fixed node sequence the evaluator solves the minimum-cost recharge plan subject to battery capacity and the duration limit. Amounts are integral because the published energy values are integral.
- Fleet size is the vehicle profile `number` attribute and is a hard constraint.
- Routes must start at `departure_node` and end at `arrival_node`.

`f` is not a field in the XML. It was identified from published no-station routes, which are validation data, not search feedback:

- Dataset A labels equal total arc energy and `γ_0 = 1`, so `f = 0` reproduces those labels.
- Datasets B and C satisfy `cost = 2.27 + γ_0 · energy` on 84 of 85 no-station routes, so `f = 2.27`.

Numerical check, recomputed by this evaluator, not copied from the XML: 65 of 66 published solutions match the label to `1e-3` and are feasible. Representatives: `SOL-C101-5` (214), `SOL-10-N10` (22.924), `SOL-C1-N030` (39.782).

Remaining discrepancy: `SOL-19-N10` is feasible under the same formula but the file label is 20.214 and the recomputed cost is 20.114. The 0.10 gap is one no-station route (`19-3-4-19`) whose label is not `2.27 + γ_0 · energy`. That file is not treated as a match.

## Goeke PDPTW-EV

Source: `dataset/goeke-2018/readme.txt`.

- Distance: Euclidean. Travel time = distance / velocity.
- Battery: consumption rate × distance. Recharge duration = energy × inverse recharging rate.
- Pickup demand is positive, delivery demand is the negation, and both ends of a request must be on the same route with pickup before delivery.
- Load is the running sum. Negative load and load above capacity are hard violations.
- The readme does not state a scalar objective and does not forbid partial recharges. Objective key: `(vehicles, distance)`. This is an explicit choice, not a published optimum.

A one-request synthetic instance is feasible when the pair is kept together and infeasible when the pair is split. Real `c101C6` still rejects delivery-before-pickup.

## Hiermann H2E-FTW

Source: `dataset/hiermann-et-al-2017-set-1/readme.txt`.

- Distance: Euclidean.
- Travel time equals distance. No speed was invented. `velocity` stays `None`.
- Station `rechargingrate` is energy per unit time, so duration = energy charged / rate.
- ICEV: fuel = distance × fuel rate, no battery constraint.
- BEV: electricity = distance × energy rate, battery bounds enforced.
- PHEV: battery energy is used first (`distance × energy rate`), then the remaining distance uses the fuel rate. This battery-first rule is a modeling choice. The readme defines the rates and prices, not the on-board control policy.
- Objective: `fixed vehicle cost + fossil-fuel price × fuel + electricity price × electric energy`.

On `c101_21`, the depot–C1–depot trajectory has travel time equal to Euclidean distance for ICEV, PHEV, and BEV, and the three objective values differ.

## Fleet availability

Finite `fleet_availability` counts are hard `FLEET` violations. Schneider, Montoya, Goeke, and Hiermann files do not publish a finite fleet size; those maps use a sentinel `10**9` and are not flagged. Bezzi uses the XML `number` attribute.

## What is not claimed

- Goeke's published objective, if it differs from vehicles-then-distance, is not in the readme.
- The PHEV battery-first policy is not a verbatim equation from Hiermann et al.
- `f = 2.27` is recovered from solution labels because the instance files omit it. One Dataset B label disagrees by 0.10.
- No optimality claim is made for any solver in this report. Published Bezzi routes were used only to check the evaluator.

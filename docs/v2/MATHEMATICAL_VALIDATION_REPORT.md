# Mathematical validation report

This report records the formulations the v2 evaluator implements, where each formula comes from, and what was checked numerically. It does not claim that every published optimum has been reproduced, and it does not treat a passing unit test as a completed benchmark campaign.

**HEAD at last update:** see git history for `MATHEMATICAL_VALIDATION_REPORT.md`.

## Evaluator versus optimizer separation

| Layer | Responsibility |
|---|---|
| Trusted evaluator (`evaluate_solution_v2` / `simulate_route`) | Validates **explicit** stops, charge amounts, technologies, loads, times, batteries. Never invents missing recharge decisions. |
| Optimizer (`backbone/charge_completion.py`, energy repair, ALNS) | Completes or inserts charging decisions before evaluation. |
| Reference validation (`problem/datasets/bezzi_reference.py`) | Loads published node sequences, reconstructs charges via the optimizer DP, then runs the trusted evaluator. |

A Bezzi solution that omits charge amounts is rejected with `CHARGE_POLICY: missing_charge_decisions` (and usually `BATTERY` as well).

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
- Symmetric `<links>` are stored in both directions. Travel time and energy stay separate matrices.
- Fleet size is the vehicle profile `number` attribute and is a hard constraint.
- Routes must start at `departure_node` and end at `arrival_node`.

### Fixed recharge cost `f` (calibrated)

`f` is **not** stored in the instance XML. It was **calibrated** from published no-station route labels (validation data only, never search feedback):

- Dataset A: labels equal total arc energy and `γ_0 = 1`, so `f = 0`.
- Datasets B and C: `cost = 2.27 + γ_0 · energy` on 84 of 85 no-station routes, so `f = 2.27`.

Limitation: `f` is a calibrated parameter recovered from solution labels, not an independently published numeric field in the XML. Papers describe `f` as battery amortization per recharge but do not embed the numeric value in these files.

### SOL-19-N10 discrepancy

Recomputed after charge reconstruction:

| Route | Published label | Formula `2.27 + γ_0·E` / DP cost |
|---|---:|---:|
| `19-3-4-19` | 3.31 | 3.21 (`E=47`) |
| other three routes | match | match |
| **total** | **20.214** | **20.114** |

Cause: the single no-station route `19-3-4-19` is labeled 0.10 above the calibrated formula that matches every other no-station route in Datasets B/C. Energy arcs sum to 47; charging exactly 47 at the depot yields 3.21. This is treated as a **data-level anomaly in the published label**, not a reason to change `f` globally. Constants were not altered to fit that one label.

### Reference check status

With charges reconstructed by the optimizer DP and then evaluated independently: **65 of 66** published solutions match the label to `1e-3` and are feasible. Representatives: `SOL-C101-5` (214), `SOL-10-N10` (22.924), `SOL-C1-N030` (39.782). `SOL-19-N10` remains the documented exception.

## Goeke PDPTW-EV

Sources: `dataset/goeke-2018/readme.txt`; Goeke (EJOR 2019) / VRP-REP PDPTW-EV description.

- Distance: Euclidean. Travel time = distance / velocity.
- Battery: consumption rate × distance. Recharge duration = energy × inverse recharging rate. Partial recharge allowed.
- Pickup demand positive, delivery the negation; same vehicle; pickup before delivery.
- Objective key: `(vehicles, distance)`. This matches the published criterion (minimize fleet size and travel distance).

## Hiermann H2E-FTW

Sources: dataset readme; Hiermann, Hartl, Puchinger, Vidal (EJOR 2019).

- Distance: Euclidean.
- Travel time equals distance (readme). No invented speed.
- Station `rechargingrate` is energy per unit time → duration = energy / rate.
- ICEV: fuel only. BEV: electricity only with battery bounds.
- PHEV: electric mode first, then fuel. This matches the paper’s greedy evaluation rule “Use electric energy mode in priority.”
- Objective: fixed vehicle cost + fossil price × fuel + electricity price × electric energy.

On `c101_21`, depot–C1–depot travel time equals Euclidean distance for ICEV, PHEV, and BEV, and the three objective values differ.

Limitation: the full paper’s layered charging-insertion heuristics for PHEVs are solver policies, not additional evaluator constraints. The evaluator accounts consumption under the electric-first rule; it does not re-optimize station placement.

## Fleet availability

Finite `fleet_availability` counts are hard `FLEET` violations. Schneider, Montoya, Goeke, and Hiermann files do not publish a finite fleet size; those maps use a sentinel `10**9`. Bezzi uses the XML `number` attribute.

## What is not claimed

- Optimality of any classical or LLM solver.
- That calibrated `f = 2.27` appears verbatim in the Bezzi XML (it does not).
- That `SOL-19-N10` matches under the calibrated formula (it does not; gap 0.10).
- Full paper competitiveness against published BKS tables (classical pilot pending / separate).

# VoltForge EVRPTW benchmark contract

Primary experimental set: the original **92 Schneider E-VRPTW instances** (36 small + 56 large). Expanded 25/50/100-customer or 168-instance variants are secondary and are not used for ranking.

## Dataset files

- Directory: `dataset/schneider/raw_instances/`
- Count: exactly 92 `*.txt` files (excluding `readme.txt`)
- Hashes: `results/manifests/instance_hashes.json` (SHA-256 of raw bytes)
- Split: `results/manifests/split.json`

Regenerate both with `uv run voltforge validate-data`.

## Charging policy

Schneider **full recharge only**. A station visit restores the battery to capacity. Partial recharge is a `CHARGE_POLICY` fault.

## Physics

- Euclidean distance: `hypot(x2 - x1, y2 - y1)` (no rounding of coordinates)
- Travel time: `distance / velocity`
- Energy: `distance * consumption_rate`
- Start-of-route battery: `vehicle.start_soc` (equal to battery capacity unless `initial_soc` is set). Do not multiply `battery_capacity * start_soc`.

## Time windows and stations

- Customer service cannot start after `due_time`.
- Depot return must meet the depot due time.
- Station ids are strings inside a route. Multiple visits to the same physical station are allowed as separate stops.
- Node ids are strings (`D0`, `C30`, …). Integer `0` is not the depot.

## Objective (laboratory ranking of a finished `solve()`)

Lexicographic:

1. feasibility
2. number of vehicles (fleet size)
3. total Euclidean distance

Distance gaps are reported at **equal fleet size**.

The generated solver may use any internal acceptance rule. The laboratory ranks complete outputs.

## Fleet

Unlimited. The solver chooses how many routes to return.

## Partitions

| Partition | Families | Use |
| --- | --- | --- |
| `DEV-DISCOVERY` | C1, R1 | Evolution only |
| `DEV-CONFIRMATION` | C2, R2, RC1 | Shortlist / winner’s-curse check. Not used to evolve. |
| Final hidden test | RC2 | Frozen until system and paper hypotheses are frozen |

Small-instance counts: 12 discovery + 18 confirmation + 6 RC2 = 36. Large: remaining 56 of the 92-instance set.

## Private anti-memorization set

Generated at evaluation time from `evrptw_autolab.problem.private` with a seed that is **not** given to agents. Same mathematical contract; perturbed geometry, windows, demand, and battery capacity. Agents may know the contract. They must not see those instance files during discovery.

## What the framework may provide

EVRPTW specification, numerical physics APIs, sandbox, compiler/runtime errors, experiment runner, evaluator, first-fault oracle.

## What the framework must not provide

Route construction, charging-repair, merge, acceptance, or a hidden fallback solution.

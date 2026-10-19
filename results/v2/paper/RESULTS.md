# VoltForge 2.0 development results

Measured on 2026-10-18. Solver behavior is commit `27278a1`. The matched-pilot runner was local uncommitted code on top of that commit; it does not change the solver. No held-out Schneider RC2 instance was evaluated. Objectives are native to each family and are not averaged across families.

## What was run

| Run | Command | Result |
|---|---|---|
| Full tests before the matched runner | `uv run pytest -q` | 221 passed, then 227 passed after the budget edits |
| Classical development panel | `uv run voltforge baselines pilot --seeds 7,11,22` | 36/39 independent rows feasible |
| Fake matched budget | `uv run pytest -q tests/test_matched_pilot.py` | 1 passed; solves were 1, 4, 4, 4 on one micro instance |
| Qwen matched pilot | `uv run voltforge experiments matched-pilot --ollama --seed 7` | completed; see below |
| Seed confirmation | `uv run python src/evrptw_autolab/experiments/confirm_matched.py` | seeds 11 and 22 on the five-instance gate |
| Extra Hiermann instances | `uv run python src/evrptw_autolab/experiments/confirm_hiermann_extra.py` | `r101_21` and `c201_21` |

Raw files:

- `results/v2/baselines/classical/run_27278a1_seed7_20261018T203033Z/pilot.json`
- `results/v2/campaigns/matched_qwen_20261018T205937Z/matched_pilot.json`
- `results/v2/campaigns/matched_qwen_20261018T205937Z/confirmation_seeds.json`
- `results/v2/campaigns/matched_qwen_20261018T205937Z/hiermann_extra.json`

## Matched budget

Model `qwen3-coder:30b`, sequential, seed 7, gate instances `c101C5`, `tc0c10s2cf1`, `C101-5`, `c101C6`, `c101_21`. Selection rule declared beforehand: conservative. The robust rule was recorded and was not used to deploy.

| Arm | Solver evaluations | LLM calls | LLM tokens |
|---|---:|---:|---:|
| Classical | 5 | 0 | 0 |
| Random grammar | 20 | 0 | 0 |
| Single-agent | 20 | 4 | 1,480 |
| Five-agent | 20 | 20 | 7,058 |

The four search-candidate counts match. Five-agent uses more model calls because each candidate has an architect, three component calls, and a critic. Those calls do not add solver evaluations.

## Seed-7 gate, native keys

Classical and both selected search bundles tied on Schneider, Montoya, Bezzi `C101-5`, and Goeke. The only movement is Hiermann `c101_21` total cost.

| Policy | Feasible | Vehicles | Distance | Total cost | Within budget |
|---|---|---:|---:|---:|---|
| Classical | yes | 20 | 2904.746852635555 | 4150.872544094683 | yes |
| Random `random_0` | yes | 20 | 2820.501821805202 | 4126.724254409762 | yes |
| Five-agent `five_1` | yes | 19 | 3115.211769915412 | 4087.7523740925253 | yes |

`random_0` is the grammar expression `route_distance_share - 0.01 * rng_value + 1.0 * rng_value`. It has no LLM component. `five_1` executed three Qwen expressions under feature schema `2026-10-18.v2`. Single-agent tied the classical key on every gate instance, so the conservative rule selected nothing from that arm.

The seed-7 rule accepted `random_0` and `five_1` because each was feasible everywhere and strictly better on one instance.

## Confirmation, which the seed-7 rule did not see

Hiermann `c101_21` total cost. Lower is better. Classical values are the frozen panel.

| Seed | Classical | Random `random_0` | Five-agent `five_1` |
|---:|---:|---:|---:|
| 7 | 4150.872544094683 | 4126.724254409762 | 4087.7523740925253 |
| 11 | 4164.778526628387 | 4122.8495525577955 | 4259.304471929594 |
| 22 | 4154.5545883236555 | 4082.91815223344 | 4282.873128098572 |

`five_1` wins seed 7 and loses seeds 11 and 22. The other four gate families stay tied with classical on seeds 11 and 22. A conservative decision on all three seeds rejects `five_1`.

`random_0` wins `c101_21` on all three seeds and ties the other gate families. On the other two already measured Hiermann instances it does not:

| Instance | Seed | Classical | Random | Five-agent |
|---|---:|---:|---:|---:|
| r101_21 | 7 | 4032.9674353081436 | 4050.1656108953894 | 4346.0440856066725 |
| r101_21 | 11 | 4047.7217930331963 | 4055.55261346549 | 4364.75132903314 |
| r101_21 | 22 | 4045.143882316208 | 4054.324034388117 | 4366.077229654057 |
| c201_21 | 7 | 1226.9918847018703 | 1239.2061800471508 | 1447.3219288594332 |
| c201_21 | 11 | 1260.5414677174158 | 1258.6995465820949 | 1461.9901997613215 |
| c201_21 | 22 | 1246.15779373392 | 1250.1173488598922 | 1464.4278349700535 |

`five_1` is worse on all six of these rows. `random_0` is worse on five and better on `c201_21` seed 11 only.

## Classical panel

Independent rows exclude duplicate Montoya file `tc0c10s3cf1`. Feasible counts: Schneider 15/15, Montoya 3/3, Goeke 9/9, Hiermann 3/3, Bezzi 6/9. Bezzi `10-N10` is infeasible on seeds 7, 11, and 22 with `CHARGE_POLICY: missing_charge_decisions`. Its nominal key is not a result. Those three runs exceeded the 12-second limit by 0.043–0.090 seconds. No other development row did.

The one-instance frozen gate was not overwritten. Seed 7 of that gate still matches it, including Hiermann `c101_21` at 4150.872544094683.

## Held-out Schneider RC2

The frozen method sent to held-out data is the classical default. The five-agent and random bundles were not frozen: confirmation showed they do not generalize. Budgets were fixed by file size before the run: C5 8s/80, C10 12s/60, C15 15s/60, 100-customer `*_21` 20s/40. Seeds 7, 11, and 22. Raw rows: `results/v2/paper/heldout_classical.json`.

24 of 42 rows are feasible. Every C5, C10, and C15 row is feasible. Among the eight 100-customer instances, only `rc201_21` (19 vehicles) and `rc202_21` (24 vehicles) are feasible on all three seeds. `rc203_21`, `rc204_21`, `rc205_21`, `rc206_21`, `rc207_21`, and `rc208_21` are infeasible inside 20 seconds. Their nominal vehicle-distance keys are not results.

## Bezzi 10-N10

Reserving the last two seconds of the 12-second budget for a final charge repair left `C101-5` feasible at 227 and left `10-N10` infeasible on seeds 7, 11, and 22, still with `CHARGE_POLICY`. That solver change was reverted. The failed measurement is `results/v2/diagnostics/bezzi_repair/summary.json`. Route energy on the saved `10-N10` solution exceeds one battery between some customers, and the station ranker finds no reachable station on the failing hop.

## Ablations

These are fresh Qwen samples on the same gate and seed, not replays of the primary bundles with one switch removed. The executed five-agent pilot does not call cross-variant transfer, so a no-transfer run would repeat the primary arm and was not launched.

| Ablation | Five-agent solves | Five-agent calls | Five-agent tokens | Five-agent deployed | Conservative outcome |
|---|---:|---:|---:|---|---|
| Primary | 20 | 20 | 7,058 | `five_1` | accepted on seed 7 only; loses seeds 11 and 22 |
| No critic | 20 | 16 | 4,652 | none | all four candidates had at least one loss |
| No evolution (1 candidate) | 5 | 5 | 1,532 | none | 0 wins, 2 losses |
| Selection disabled | 20 | 20 | 7,353 | `five_3` | feasibility regression, 0 wins, 3 losses |

Disabling selection deploys the last bundle. That bundle is infeasible on part of the gate. The conservative rule rejects it. Single-agent again had no accepted candidate when selection was on, and the disabled rule deployed a bundle with no strict improvement. Files: `matched_qwen_no_critic_20261018T234819Z`, `matched_qwen_no_evolution_20261018T235444Z`, `matched_qwen_no_selection_20261018T235642Z`.

## What is not claimed

- Five-agent search did not beat classical or the random grammar once a second seed was measured.
- Single-agent search did not beat classical on the seed-7 gate.
- No policy was frozen for held-out evaluation. Schneider RC2 remains untouched.
- `10-N10` is still an open classical charging failure.
- Hiermann `c101_21` remains about 20 vehicles under the classical solver. The seed-7 drop to 19 vehicles belonged to `five_1` and did not replicate.
- No significance test is reported. The comparisons are paired instance-seed rows.

# Recovery results

Decision: **FEASIBILITY_RECOVERED**.

LLM superiority was not demonstrated. No ablation against the frozen classical backbone or a random grammar was run. Stage 3 confirmation and Stage 4 scaling were not started.

## Baseline before these edits

The live five-agent pilot at `qwen3-coder:30b` (`sha256-1194192cf2a187eb02722edcc3f77b11d21f537048ce04b67ccf8ba78863006a`) was 0/5 feasible. Those files remain in `results/agentic_v2/`. Bezzi `C101-5` failed with `CHARGE_POLICY` because a station was reached on an empty battery. The route builder could not attach a charge amount to the departure depot.

The classical 39/39 development freeze is a different method and is not an agent result.

## What was measured after the contract fix

Parent commit of the tree: `93e1e3e`. The recovery edits were not committed when these commands ran.

### Stage 0 and Stage 1

```powershell
uv run pytest tests/test_recovery_contracts.py tests/test_agentic_v2.py tests/test_bezzi_charge_plans.py tests/test_evaluator_v2.py -q
```

`tests/test_recovery_contracts.py` covers an explicit Bezzi depot charge that the evaluator accepts (objective 11 on the frozen micro instance), rejection of a bad edit without losing that charge, atomic pickup-delivery relocation, published energy matrices in the problem context, labeled recharge DP, and mixed-fleet fixed cost 105 when the assignment list is short.

### Deterministic customer packing, no model calls

`results/recovery_v1/deterministic_stage1.json`

Customers were packed without calling an LLM and without calling ALNS. Battery or charge-policy failures were passed to `repair_energy` (at most 12 station insertions) and the Bezzi DP. Bezzi used two routes because `type_0` is limited to 2 vehicles.

| Family | Instance | Feasible | Objective | Charging |
| --- | --- | --- | --- | --- |
| Schneider | c101C5 | yes | vehicles 5, distance 296.0921118198048 | none required |
| Montoya | tc0c10s2cf1 | yes | duration 43.453874454811256 | deterministic energy repair |
| Bezzi | C101-5 | yes | recharge cost 225 | deterministic energy repair |
| Goeke | c101C6 | yes | vehicles 3, distance 270.9864386050047 | deterministic energy repair |

These rows are human-authored packings plus deterministic charging. They are not LLM solutions.

### Stage 2 live model, 20 calls

```powershell
# four instances, max_rounds=1, max_llm_calls=5, deterministic_charging=True
```

`results/recovery_v1/llm_stage2.json`. Model digest as above. `classical_alns_used` is false. Attribution on every row is `agentic_customer_plan_with_deterministic_charge_repair`.

| Family | Feasible | Calls | Tokens | Wall (s) | First fault or objective |
| --- | --- | --- | --- | --- | --- |
| Schneider c101C5 | no | 5 | 5239 | 24.901 | WINDOW, lateness 157.536649 at due 325 |
| Montoya tc0c10s2cf1 | no | 5 | 8045 | 5.520 | BATTERY, arrival -5190.573375 after 8 station-insertion attempts |
| Bezzi C101-5 | yes | 5 | 6372 | 4.485 | recharge cost 225 |
| Goeke c101C6 | no | 5 | 6369 | 4.267 | WINDOW, lateness 157.536649 at due 325 |

Total model calls: 20. Hiermann `c101_21` was not run.

The feasible Bezzi cost equals the deterministic two-vehicle pack. This pilot does not show a better objective than that pack, and it does not show that the model invented the charge amounts. The charge amounts come from `repair_energy` and the Bezzi DP after the model proposed customers.

## Remaining weaknesses

- Schneider and Goeke still fail time windows when the model puts incompatible customers on one route. Charging repair does not move customers.
- Montoya's model sequence stayed energy-infeasible after 8 station insertions.
- Generated code still runs in a subprocess, not a container.
- Track B (LLM-designed heuristic components versus the frozen backbone) was not rerun.
- Seeds 7, 11, and 22, Schneider RC2, and the 426-instance manifest were not used.

## Commands that were not run

No classical ALNS solve. No increase of the 5-call instance cap. No Hiermann 100-customer run.

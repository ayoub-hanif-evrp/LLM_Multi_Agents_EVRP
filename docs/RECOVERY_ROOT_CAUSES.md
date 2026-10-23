# Recovery root causes

Confirmed against the source and a regression test. The previous 0/5 agentic pilot is unchanged in `results/agentic_v2/`.

## 1. Bezzi departure-depot charge could not be expressed

`route_simulator.py` starts a multi-technology vehicle at battery 0. It charges the first stop only when that stop is the depot, the capability is multi-technology, and `charge_amount` is set.

`agentic_v2/actions.py` built every route as `RouteStopV2(depot, vehicle, "depot")` and ignored a `depot_charge` field. `insert_charges` only inserted station stops. An agent could not state the initial depot charge the evaluator requires.

Impact: prompting the charging agent to pick a station cannot create the missing departure-depot decision. A route that is energy-feasible after an explicit depot charge was reported as `CHARGE_POLICY` / negative battery.

Evidence: `tests/test_recovery_contracts.py::test_agent_can_express_a_feasible_bezzi_depot_charge` failed before the fix because `charge_amount` stayed `None`. It now expects amount 8, technology `"0"`, and an independent objective of 11.

The evaluator was not changed to start Bezzi vehicles full.

## 2. Published matrices and the empty-start rule were not in the agent context

`instance_context.summarize_instance` sent coordinates and a Euclidean travel table. Bezzi distance, time, and energy come from matrices. The prompt did not state that the battery starts empty until an explicit depot charge.

`problem_context` now records the initial-battery rule, fleet limits, charging technologies, nonlinear curves when present, and the energy, travel-time, and distance matrices. Prompt summaries omit matrices above 20 nodes. `spec_payload` still gives the generated solver the full matrices.

## 3. Objective cost used an incomplete assignment list

`_vehicle_for_route` resolves a missing assignment from the stop's vehicle type. `_objective` previously summed `solution.vehicle_assignments` and, for Hiermann, ignored routes past a short list. A mixed fleet could be simulated with the correct types and then costed as if only the listed vehicles existed.

`evaluate_solution_v2` now passes the resolved type of every route into `_objective`. `test_partial_vehicle_assignment_uses_each_resolved_type` expects fixed cost 100 + 5.

## 4. Actions could stick when they were invalid or worse

Relocation used the first stop with a matching node id and moved one customer. A pickup and its delivery could be split. A failed edit changed the object the caller still held.

`apply_transaction` clones the candidate, rejects unknown or ambiguous identifiers, moves a same-vehicle pickup-delivery pair together, and commits only a feasible trial that does not worsen the native objective. The original depot charge is still present after a rejected edit.

## 5. Charging on a fixed customer sequence is a deterministic subproblem

`complete_missing_charges` calls the existing Bezzi recharge DP when amounts are absent. It does not call ALNS. The metadata is `deterministic_bezzi_recharge_dp` and `agentic_customer_plan_with_deterministic_charge_repair`.

`certify_charging(..., insert_stations=True)` may then call `energy_repair.repair_energy` with at most 8 insertions. That path is off unless the caller sets `deterministic_charging=True`. It is labeled `deterministic_energy_repair`. It is not an LLM solution and not a classical ALNS solve.

## 6. Generated code is still a subprocess

No container runtime is wired in. `executor.py` still runs generated Python in a subprocess after the static scan. That is process isolation, not a security sandbox. Untrusted code should not be given host credentials. This recovery did not add a container runner because none is part of the project environment, and the feasibility defect above did not depend on it.

## What was not a model failure

The 0/5 pilot also contains real routing mistakes: one Schneider route cannot meet the time windows, and a station inserted after the battery is already negative does not repair it. Those remain model or search failures. They are separate from the Bezzi depot-charge interface, which blocked a reasonable depot decision from being represented at all.

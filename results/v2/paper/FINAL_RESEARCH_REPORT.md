# VoltForge 2.0 final research report

Generated from raw artifacts at `63cc1d65edc15d01d6a8fe51a14f000f86f56c5a`.
Native objectives are not averaged across families. Infeasible nominal keys are not results.
Classical improvements are not attributed to the LLM.

## A. Engineering

Phases A and B are commit `c2de5a05a9cc27a4aad65f6895231c13b580790a`.
The local suite after that commit was 230 passed. This report does not replace that run.
See `ENGINEERING_VALIDATION.json` for the artifact checks executed with this package.

## B. Classical backbone

Independent development rows at the frozen solver, excluding duplicate `tc0c10s3cf1`: 39/39 feasible.
Parent runtime within limit plus 0.05s: 39/39.
By family: bezzi 9/9, goeke 9/9, hiermann 3/3, montoya 3/3, schneider 15/15.
Seed-7 gate keys remain the frozen baseline where that baseline was already feasible, including Bezzi `C101-5` at 227.
Bezzi `10-N10` is feasible on seeds 7, 11, and 22 in `results/v2/diagnostics/bezzi_pack/summary.json` and in this freeze.
Those costs are classical pack plus ALNS. They are not the published 22.924 reference and they are not an LLM result.
The historical expanded panel still records the earlier infeasible `10-N10` rows.
Large Schneider discovery profile, not RC2: c103C15 feasible=True fault=OK; r102C10 feasible=True fault=OK; c101_21 feasible=False fault=BATTERY.
That profile is the trace before route-local construction. Seed 7 of c101_21 is then feasible inside 20 seconds at 39 vehicles in results/v2/diagnostics/large_development/c101_21_route_local.json.
The 39-vehicle key is a classical feasible result, not an optimized fleet and not an LLM result.

## C. Specialist-role schedule, seed 7

Design: Rotating specialist prompts. The five-agent arm adds a critic and does not call an architect.
Selection: {"random_evolution": "random_g2", "single_agent": "single_g0", "five_agent": "five_g0"}.
This is not a unified-agent versus five-role comparison. Both language-model arms used specialist prompts.
The accepted insertion returns are `return max(0, capacity_slack - demand) + abs(delta_distance)` for single_g0 and the same expression plus `float(ready_time > due_time)` for five_g0. That added term is zero when ready_time is at or before due_time.

## C2. Unified designer versus architect, specialist, and critic

Each generation calls the architect, the specialist for the one scheduled component, and the critic. Routing, charging, and search rotate across generations. All five roles are not called in the same generation.

Artifact `results/v2/campaigns/generational_qwen_20261019T190105Z/generational.json`, discovery seed 7, wall 361.026s.
Selection: {"random_evolution": "random_g2", "single_agent": "single_g0", "five_agent": "five_g0"}.
Tokens: {"single_agent": 1891, "five_agent": 4455, "random_evolution": 0, "classical": 0}. Solver evaluations: {"classical": 5, "random_evolution": 20, "single_agent": 20, "five_agent": 20}.
single_agent single_g0 role=unified c101_21=[4087.7523740925253] insertion=`def insertion_score(delta_distance: float, due_time: float, ready_time: float, demand: float, capacity_slack: float) -> float:     return max(0, capacity_slack) + min(1000, delta_distance) - 0.1 * abs(ready_time - due_time)`.
five_agent five_g0 role=routing c101_21=[4087.7523740925253] insertion=`def insertion_score(delta_distance: float, due_time: float, ready_time: float, demand: float, capacity_slack: float) -> float:     return max(0, capacity_slack - demand) + abs(delta_distance)`.
Architect hypothesis: The insertion_score component will serve as a metric for quantifying the effectiveness of insertion operations, likely measuring factors such as insertion speed, resource utilization, or impact on existing data structures, and may be integrated with existing performance monitoring systems to provide real-time feedback on insertion operation quality.

Artifact `results/v2/campaigns/generational_qwen_20261019T190854Z/generational.json`, discovery seed 19, wall 360.822s.
Selection: {"random_evolution": null, "single_agent": "single_g0", "five_agent": null}.
Tokens: {"single_agent": 1920, "five_agent": 4430, "random_evolution": 0, "classical": 0}. Solver evaluations: {"classical": 5, "random_evolution": 20, "single_agent": 20, "five_agent": 20}.
single_agent single_g0 role=unified c101_21=[4036.867946210605] insertion=`def insertion_score(delta_distance: float, due_time: float, ready_time: float, demand: float, capacity_slack: float) -> float:     return max(0, capacity_slack) + min(1000, delta_distance) - 0.1 * abs(ready_time - due_time)`.
five_agent selected nothing.

Role-split three-seed file: `confirmation_schneider_role_split.json`.
Promoted: ['random_evolution:random_g2'].
- random_evolution random_g2: three-seed accepted=True reason=accepted_no_regression wins=3 losses=0
- single_agent single_g0: three-seed accepted=False reason=objective_regression wins=2 losses=1
- five_agent five_g0: three-seed accepted=False reason=objective_regression wins=2 losses=1


## D. Five-agent evolution

The 2026-10-18 matched pilot accepted `five_1` on seed 7 and that bundle lost Hiermann `c101_21` on seeds 11 and 22.
It did not beat classical or the random grammar once those seeds were measured.
The 2026-10-19 generational arm uses the same conservative rule, the same gate, and the same candidate count.
Five-agent token use in that schedule is the critic call. The architect was not called.
Equal solver evaluations were enforced. Token counts are measured and are not a matched compute budget.

## E. What generalizes

The bullets below are the specialist-schedule confirmation in `confirmation_schneider.json`, not the role-split confirmation in section C2.
The classical default remains the deployed scoring policy.
A grammar candidate can pass the development rule without being an LLM result.
- random_evolution random_g2: three-seed accepted=True reason=accepted_no_regression wins=3 losses=0
-   seed 11 c101_21 key=[4122.8495525577955] within_budget=True
-   seed 22 c101_21 key=[4082.91815223344] within_budget=True
- single_agent single_g0: three-seed accepted=False reason=objective_regression wins=2 losses=1
-   seed 11 c101_21 key=[4259.304471929594] within_budget=True
-   seed 22 c101_21 key=[4044.2164307328712] within_budget=True
- five_agent five_g0: three-seed accepted=False reason=objective_regression wins=2 losses=1
-   seed 11 c101_21 key=[4259.304471929594] within_budget=True
-   seed 22 c101_21 key=[4044.2164307328712] within_budget=True
- confirmation paired rows tied=9 differed=0
Policies sent to confirmation after the three-seed decision: ['random_evolution:random_g2'].
Classical confirmation rows feasible: 9/9.
Confirmation ids are `c206C5`, `r202C5`, and `r203C5`. `rc105C5` stays on the development panel and was not used as confirmation.
Schneider RC2 remains the held-out split and was not retuned. The earlier classical held-out file is unchanged: 24/42 feasible, 18/42 feasible and inside budget.

## F. Quantitative results

Tables in this directory are regenerated from the raw JSON named in `PROVENANCE.jsonl`.
Published Schneider CPLEX keys live in `evrptw_autolab.evaluation.literature` and are references only.
Some measured keys match those published figures at the reported rounding, including development `r105C5` and confirmation `r203C5`.
Others do not, including development `c101C5` and confirmation `c206C5` and `r202C5`.
No best-known-solution claim is made.
Model digest recorded for the generational run: sha256-1194192cf2a187eb02722edcc3f77b11d21f537048ce04b67ccf8ba78863006a.

## G. Limitations

The comparison is exploratory. Five gate instances and one discovery seed do not support a significance claim.
The 14:59 UTC artifact used full-bundle proposals and deployed the first accepted candidate. It is historical.
The 2026-10-19 18:27 and 18:38 UTC runs used specialist role prompts on a rotating component. The five-agent arm added a critic and did not call an architect.
Seed 13 of that same schedule accepted no candidate.
A later run with workflow unified_versus_architect_specialist_critic is reported only when its artifact is present.
Critic text is not a causal explanation.
Route-local construction makes development c101_21 seed 7 feasible inside 20 seconds at 39 vehicles. That fleet is not an optimized result. RC2 was not used to make this change.
Hiermann `c101_21` remains a 20-vehicle classical solution on the frozen seed-7 gate.
FakeBackend output is plumbing and is not model evidence.

## H. Publication files

Ready for review as an honest negative-or-limited package: the CSV tables, `STATISTICS.json`, `PROTOCOL.md`, `DATASET_SPLITS.json`, `REPRODUCE.md`, and this report.
Not ready as a superiority paper. No abstract claims that five-agent search beats classical, random, or single-agent search.

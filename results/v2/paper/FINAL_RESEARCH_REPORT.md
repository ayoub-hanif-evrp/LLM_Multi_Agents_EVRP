# VoltForge 2.0 final research report

Generated from raw artifacts at `c2de5a05a9cc27a4aad65f6895231c13b580790a`.
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
The 100-customer discovery instance `c101_21` still times out with a battery violation inside 20 seconds. No further search was added.

## C. Single-agent evolution

Seed-7 generational selection: {"random_evolution": "random_g2", "single_agent": null, "five_agent": "five_g3"}.
Generation 0 is the one-shot control. A candidate is accepted only by the conservative rule and only if a probe score changed.
The earlier matched pilot on solver `27278a1` also selected nothing from the single-agent arm.

## D. Five-agent evolution

The 2026-10-18 matched pilot accepted `five_1` on seed 7 and that bundle lost Hiermann `c101_21` on seeds 11 and 22.
It did not beat classical or the random grammar once those seeds were measured.
The 2026-10-19 generational arm uses the same conservative rule, the same gate, and the same candidate count.
Five-agent token use is higher because the architect, component calls, and critic are extra model calls. They do not add solver evaluations.
A resource-matched claim is not supported: equal solver evaluations were enforced, and the extra tokens were measured rather than matched by giving the other arms more model calls.

## E. What generalizes

The classical default remains the deployed scoring policy.
A grammar candidate can pass the development rule without being an LLM result.
- random_evolution random_g2: three-seed accepted=True reason=accepted_no_regression wins=3 losses=0
-   seed 11 c101_21 key=[4122.8495525577955] within_budget=True
-   seed 22 c101_21 key=[4082.91815223344] within_budget=True
- five_agent five_g3: three-seed accepted=False reason=objective_regression wins=2 losses=1
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
Single-agent and five-agent proposals are new bundles conditioned on feedback text. Only the random arm mutates the accepted parent's source.
Critic text is not a causal explanation.
Large 100-customer Schneider instances remain battery-infeasible inside the declared 20-second budget.
Hiermann `c101_21` remains a 20-vehicle classical solution on the frozen seed-7 gate.
FakeBackend output is plumbing and is not model evidence.

## H. Publication files

Ready for review as an honest negative-or-limited package: the CSV tables, `STATISTICS.json`, `PROTOCOL.md`, `DATASET_SPLITS.json`, `REPRODUCE.md`, and this report.
Not ready as a superiority paper. No abstract claims that five-agent search beats classical, random, or single-agent search.

# Method and experiments

## Claim that the code supports

The classical ALNS repair can be given a versioned insertion policy without handing feasibility or the native objective to generated code. On one Schneider micro-instance, a deterministic policy changes the repaired position and both routes stay feasible. The expression `delta_distance + 0.01 * due_time` does not change that ranking, because due time is constant for the customer.

On a two-route Hiermann micro, `delta_distance` inserts the customer on the ICE and `incremental_energy_cost` inserts it on the BEV. Both repairs are feasible. The BEV repair has the lower native cost, 60.9685424949238 against 72.2842712474619. Goeke pair repair can use the same scorer. `battery_margin` is a simulated arrival state of charge, not a charging price.

No multi-agent advantage is claimed. No held-out Schneider RC2 run is claimed. The Hiermann long-route rule from the previous measurement improved `c101_21` on seeds 7, 11, and 22 and lost on `r101_21` and `c201_21`. It is not promoted. `marginal_removal_distance` wins seven of the nine predeclared pairs and loses `r101_21` seeds 11 and 22, so it is labeled `NOT_GENERALIZED` and was not edited.

## What is borrowed

Ropke and Pisinger (2006) supply the destroy-and-repair loop this solver already had. Keskin and Çatay (2016) motivate charging-aware removal. v4 records `battery_margin` from the existing route simulator and does not add a station-detour formula. Montoya et al. (2017) is the reason nonlinear charging stays in the existing dynamic program. FunSearch, Evolution of Heuristics, and ReEvo supply the outer pattern: small executable scores, a random grammar from the same names, and rejection of a score that does not change the recorded decision.

The project-specific piece is the split between the historical objective ranking and schema `2026-10-24.v4`, whose features are limited to values that vary across the real candidate set.

## Questions

RQ1 through RQ5 in the recovery brief are not answered by the micro repair. A later run can answer them only on the same v4 repair path, with the random grammar wrapped by `wrap_expression`, and with confirmation instances held out of the prompt.

## Reproduction

```text
uv run pytest tests/test_real_policy_decisions.py -q
uv run voltforge experiments policy-recovery-v4
uv run voltforge experiments policy-recovery-v4 --live
```

`uv run voltforge experiments policy-recovery-v4 --live` was run once on the one-route micro: 3 calls, 708 tokens, no position change, file `results/recovery_v4/live.json`. It was run again after the two-route gate: 4 calls, 1052 tokens. The routing expression placed the customer on the BEV at cost 60.9685424949238. The single-agent and random expressions stayed on the ICE at cost 72.2842712474619. That file is `results/recovery_v4/live_two_route.json`. The critic was not called. The command does not replace `results/recovery_v2/` or the classical pilot files.

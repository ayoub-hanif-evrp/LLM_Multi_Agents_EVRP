# Protocol

Selection rule, declared before confirmation: conservative.
Accept only if feasibility is preserved on every development pair, the candidate is not strictly worse on any pair, and it is strictly better on at least one pair.
A candidate whose probe scores do not change is rejected as `no_decision_change`.
The robust one-third rule is recorded and is not the deployment rule.
Search arms receive the same candidate count, the same gate instances, the same per-instance time limits, and the same evaluator.
Each generation replaces one scheduled component of the accepted parent. The schedule cycles insertion, station, then removal.
Generation 0 receives no fitness feedback. Later generations do.
Among conservatively accepted candidates, the one with the most wins is deployed. An earlier generation wins a tie.
The critic receives the classical objective keys. It does not add a solver evaluation.
A feasible candidate that misses completed_within_budget cannot beat an on-time baseline. Recorded campaigns were accepted before this deadline check.
Score changes are recorded separately from ranking changes and from the move selected during construction.
The 2026-10-19 18:27 and 18:38 UTC artifacts use specialist prompts. Five-agent's extra call in those artifacts is the critic, not an architect.
The current code workflow is unified_versus_architect_specialist_critic. It is reported only from artifacts that record that workflow.
Random, single-agent, and five-agent search use the same expression language and the same scheduled component.
Confirmation ids `c206C5`, `r202C5`, and `r203C5` are loaded only after the three-seed decision file is written.
If no learned policy passes that decision, confirmation is classical only.
Schneider RC2 is not used to choose a policy.

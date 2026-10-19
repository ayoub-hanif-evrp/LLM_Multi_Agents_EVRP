# Protocol

Selection rule, declared before confirmation: conservative.
Accept only if feasibility is preserved on every development pair, the candidate is not strictly worse on any pair, and it is strictly better on at least one pair.
A candidate whose probe scores do not change is rejected as `no_decision_change`.
The robust one-third rule is recorded and is not the deployment rule.
Search arms receive the same candidate count, the same gate instances, the same per-instance time limits, and the same evaluator.
Generation 0 receives no fitness feedback. Later generations do.
The critic does not add a solver evaluation.
Random, single-agent, and five-agent search use the same expression language.
Confirmation ids `c206C5`, `r202C5`, and `r203C5` are loaded only after the three-seed decision file is written.
If no learned policy passes that decision, confirmation is classical only.
Schneider RC2 is not used to choose a policy.

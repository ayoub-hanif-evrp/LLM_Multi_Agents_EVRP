# Operator specification

An operator is an `OperatorSpec` in `src/evrptw_autolab/discovery/schemas.py`.

Hard compatibility is the list of `CapabilityFlags` names in `required_capabilities` and `forbidden_capabilities`. `compatibility_failures` in `transfer/hard_compatibility.py` is the only acceptance check. It does not read an instance name and it does not call a model.

`applicability_rule` decides whether the operator is tried. `candidate_scoring_policy` ranks screened insertions and is also a restricted expression. `repair_greedy` uses both when it receives an `OperatorSpec`. A non-positive rule, a capability failure, or an illegal score keeps the classical insertion. The default solver does not pass an operator.

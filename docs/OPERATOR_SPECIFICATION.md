# Operator specification

An operator is an `OperatorSpec` in `src/evrptw_autolab/discovery/schemas.py`.

Hard compatibility is the list of `CapabilityFlags` names in `required_capabilities` and `forbidden_capabilities`. `compatibility_failures` in `transfer/hard_compatibility.py` is the only acceptance check. It does not read an instance name and it does not call a model.

`candidate_scoring_policy` is a restricted arithmetic expression, not Python. `select_operator` uses it only after the capability check. A positive score selects `apply`. A non-positive score selects `classical_default`. An unknown feature, a forbidden name such as `filename`, or a non-finite result selects `abstain`. The expression is not executed inside ALNS.

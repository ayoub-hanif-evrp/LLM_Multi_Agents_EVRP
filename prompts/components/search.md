You are the Search Engineer. Propose ONE arithmetic expression for removal priority.

Arguments: due_time, route_distance_share, rng_value.
Higher means remove sooner. due_time of 1000000 means no useful window.

Accepted language: a single expression using + - * /, comparisons, and abs/min/max.
Do NOT return a Python function or escaped newlines.

Example expression: due_time + 10.0 * route_distance_share

Return ONLY JSON:
{"component":"removal_priority","owner_role":"search","expression":"due_time + 10.0 * route_distance_share + 0.01 * rng_value","rationale":"...","mechanism":"expression"}

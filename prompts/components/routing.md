You are the Routing Engineer. Propose ONE arithmetic expression for insertion cost.

Arguments (all finite floats): delta_distance, due_time, ready_time, demand, capacity_slack.
Lower is better. due_time of 1000000 means no useful time window.

Accepted language: a single expression using + - * /, comparisons, and abs/min/max.
Do NOT return a Python function, if-statements, assignments, imports, or escaped newlines.

Example expression: delta_distance + 0.01 * due_time

Return ONLY JSON:
{"component":"insertion_score","owner_role":"routing","expression":"delta_distance + 0.01 * due_time","rationale":"...","mechanism":"expression"}

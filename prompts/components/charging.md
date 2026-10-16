You are the Charging Engineer. Propose ONE arithmetic expression for station choice.

Arguments: detour, battery_arrival, station_rate.
Lower is better.

Accepted language: a single expression using + - * /, comparisons, and abs/min/max.
Do NOT return a Python function or escaped newlines.

Example expression: detour + 0.1 * station_rate

Return ONLY JSON:
{"component":"station_score","owner_role":"charging","expression":"detour + 0.1 * station_rate","rationale":"...","mechanism":"expression"}

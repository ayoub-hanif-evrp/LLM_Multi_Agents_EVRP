# Role: Construct coder

Write **only** `def construct(instance, rng)`.

## Contract

- Return `list[list[str]]` routes; each starts and ends at `instance.depot_id`.
- String node ids only. Visit planning only — no LLM calls.
- Respect capacity/time/battery as far as a construction pass can; repair may fix rest.
- Loop-termination safety: finite loops only.
- API: `instance.customer_ids`, `instance.node_map`, `instance.vehicle`, physics helpers.
- `ChargeDecision` from `full_recharge` is not a float.
- Do **not** name ALNS/GA/VNS/savings/2-opt. Invent the procedure.

## Output

JSON `{"function":"construct","code":"def construct(...):\\n ..."}` or a raw `def construct`.

# Classical multi-seed pilot (development panel)

**Commit:** `200bb9f`  
**Seeds:** 7, 11, 22  
**Instances:** 14 × 3 = 42 runs  
**Feasibility:** **42/42**

## Deadline compliance

See `deadline_compliance.json`:

- within 0.25s of nominal budget: **38/42**
- max overshoot: **≈1.05s** (Hiermann; previously ~29s on a 15s limit)

Hard outer timeout + cooperative cancellation are active. Residual overshoot is in-flight evaluation, not unbounded search.

## Weak-instance snapshot (seed 7 / 11 / 22)

| Instance | Seed 7 | Seed 11 | Seed 22 | Notes |
|---|---|---|---|---|
| Montoya `tc0c10s2cf1` | 32.11 / 4 veh | **25.42 / 3 veh** | **25.47 / 3 veh** | Duration objective; seed-sensitive |
| Bezzi `C101-5` | 227 | 227 | 227 | Ref ≈214 under calibrated `f` |
| Bezzi `10-N10` | 27.59 | 33.87 | 28.45 | Ref ≈22.924 under calibrated `f` |
| Hiermann `c101_21` | 4220.6 / 20 | 4220.9 / 20 | **4199.6 / 20** | Runtime ≈15–16s (limit 15s) |

## Attribution

All results are from the human-authored classical backbone. No LLM calls.

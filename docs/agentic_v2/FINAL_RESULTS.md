# Agentic solver results

Live model: `qwen3-coder:30b`, digest `sha256-1194192cf2a187eb02722edcc3f77b11d21f537048ce04b67ccf8ba78863006a`.

The independent evaluator accepted none of the five representative instances. No classical ALNS solution was substituted. `classical_alns_used` is false on every row.

| Family | Instance | Mode | Status | First fault | Calls | Tokens | Wall (s) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Schneider | c101C5 | explicit routes, then generated code | INFEASIBLE_OUTPUT | CHARGE_POLICY, S5 reached with a negative battery | 13 | 12558 | 19.687 |
| Montoya | tc0c10s2cf1 | explicit routes | INFEASIBLE_OUTPUT | CHARGE_POLICY, station 11 reached with a negative battery | 13 | 16576 | 18.103 |
| Bezzi | C101-5 | explicit routes | INFEASIBLE_OUTPUT | CHARGE_POLICY, station 5 reached with a negative battery | 13 | 10829 | 17.811 |
| Goeke | c101C6 | explicit routes | INFEASIBLE_OUTPUT | CHARGE_POLICY, S0 reached with a negative battery | 13 | 13452 | 16.418 |
| Hiermann | c101_21 | generated solver | INFEASIBLE_OUTPUT | WINDOW, service started 49.529 after the due time | 11 | 32154 | 20.940 |

Records are in `results/agentic_v2/runs/`. Earlier Schneider attempts are kept as `schneider_c101C5_attempt1.json` through `attempt4.json`. The first attempt was labeled `MODEL_FAILURE` because an infeasible route was discarded. Later attempts keep the evaluator fault.

What the traces do show:

- All five roles ran on the live model. The architect named the native objective for each family.
- Schneider routes use the real customers `C12`, `C30`, `C64`, `C85`, and `C100`. The generated repair reads `instance["travel"]` and checks battery and due times. It still returned one route. A separate vehicle for each customer fits the battery and the windows; the model did not emit that plan.
- Montoya inserted station `11` with `target_soc` 16000. The station is after the battery is already negative, so the nonlinear charge is not a feasible decision.
- Bezzi inserted station `5` with `charge_amount` 77 and `charge_technology` `"1"`. The amount and technology are explicit. The arrival battery is negative, so the recharge cost on that row is not a feasible objective.
- Goeke emitted pickup and delivery events (`C12` pickup, `C30` delivery, and two further pairs). The first fault is still the charging arrival, so this run does not establish precedence.
- Hiermann's generated solver returned 20 routes. The recorded cost key is 5458.472203722316 on an infeasible solution. It is not a feasible fleet cost.

## Engineering checks

`tests/test_agentic_v2.py` uses `FakeBackend`. Those tests pass: five roles, a saved infeasible fault, a missing-customer repair, generated-code execution, rejection of `solve_classical`, a battery fault repaired by generated code, Schneider `c101C5` loading, and checkpoint detection.

`components/expressions.py` annotates the v3 default-formula dictionary. `mypy` reports no issues on that file, the agentic package, and `cli.py`.

## What was not run

The 426-instance benchmark was not started. Another multi-hour repair campaign was not started. A fair comparison against single-agent generation and classical ALNS has not been measured for this solver. The older 39/39 feasibility freeze remains a classical backbone result.

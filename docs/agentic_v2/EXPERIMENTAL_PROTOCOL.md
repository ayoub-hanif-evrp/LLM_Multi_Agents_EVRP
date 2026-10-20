# Experimental protocol

## Question

Can five LLM agents, checked by the existing evaluator, produce an independently feasible solution on one published instance from each EVRP family?

## Instances

| Family | Instance | What must hold |
| --- | --- | --- |
| Schneider | c101C5 | vehicle count, then distance; full recharge |
| Montoya | tc0c10s2cf1 | nonlinear charging; duration objective |
| Bezzi | C101-5 | explicit charge amount and technology; recharge cost |
| Goeke | c101C6 | pickup before delivery on the same vehicle |
| Hiermann | c101_21 | heterogeneous fleet; economic cost |

## Method

Model profile `qwen3_coder_30b` (`qwen3-coder:30b` on local Ollama). One instance at a time. At most 3 repair rounds and 16 model calls. The incumbent is the best feasible evaluator report. An infeasible attempt does not replace it.

## What is not claimed

- The classical 39/39 freeze is not an agent result.
- A generated solver that calls ALNS would be labeled hybrid. This protocol forbids that call.
- Families are not averaged.
- Held-out Schneider RC2 is not used.
- Completing this pilot is not a claim about the other 421 instances.

## Status codes

`FEASIBLE`, `INFEASIBLE_OUTPUT`, `TIMEOUT`, `EXECUTION_ERROR`, `MODEL_FAILURE`, `PARSE_ERROR`, `NOT_RUN_BUDGET`.

## Ablations

Not run in this first pilot. Later comparisons, under the same call and time budget, are: one routing agent, five agents, five agents without the critic, five agents without the charging role, and classical ALNS as its own row.

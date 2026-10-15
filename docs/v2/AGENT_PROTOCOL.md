# Agent Protocol — Component Synthesis (Milestone 5)

## Roles (same five logical agents)

| Role | Owns | Output |
|------|------|--------|
| Architect | Plan | `AlgorithmPlan` |
| Routing | `insertion_score` | `ComponentProposal` |
| Charging | `station_score` | `ComponentProposal` |
| Search | `removal_priority` | `ComponentProposal` |
| Critic | Decision | `CandidateDecision` |

One owner per component. Agents do not silently edit another role's code.

## Trust

1. Subprocess validates each component (AST + numeric smoke).
2. Classical backbone executes search.
3. `evaluate_solution_v2` alone decides feasibility.
4. Critic `ACCEPT` is downgraded to `REJECT` if the evaluator reports infeasible.

## Smoke

```bash
uv run voltforge components smoke --fake
```

Do not start multi-hour Ollama campaigns from this command.

# P1.3 Experiment A — Cross-model repair (common 3/4 seed)

**Not** end-to-end synthesis. Same Qwen seed, same P1.3 protocol, `run_id=repair01`.

| Model | Initial | Final best | 4/4 | Calls | Prompt tok | Compl. tok | Non-NO_OP patches | Architect | Regressions | Winning agent | Final hash |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- | --- |
| `qwen2.5-coder:7b` | 3/4 | 3/4 | ❌ | 6 | 10854 | 1018 | 1 | yes | 0 | — | `6b819e904a772f8e` |
| `deepseek-coder:6.7b` | 3/4 | 4/4 | ✅ | 3 | 7189 | 1168 | 2 | no | 0 | search/coding_repair | `50fd471ee248c9c1` |
| `codellama:7b` | 3/4 | 3/4 | ❌ | 9 | 20268 | 3042 | 1 | yes | 0 | — | `6b819e904a772f8e` |

## First 4/4 freeze

- Artifact: `results/md/artifacts/p1_3/P1_3_FIRST_4OF4_SOLVER/solver.py`
- Source: DeepSeek-Coder 6.7B / repair01
- Hash: `50fd471ee248c9c1`

## Unchanged evaluation on all Schneider C5 (12 instances)

**12/12 feasible**

- `c101C5`: OK
- `c103C5`: OK
- `c206C5`: OK
- `c208C5`: OK
- `r104C5`: OK
- `r105C5`: OK
- `r202C5`: OK
- `r203C5`: OK
- `rc105C5`: OK
- `rc108C5`: OK
- `rc204C5`: OK
- `rc208C5`: OK

## Classification

P1.3 is **guided trace-based repair** (Critic still mentions pre-service waiting generically).
This screening does **not** claim empty-workspace autonomous discovery.

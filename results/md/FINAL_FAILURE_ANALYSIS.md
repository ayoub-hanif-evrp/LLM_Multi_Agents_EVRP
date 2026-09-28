# FINAL failure analysis

Distributions from MCB V1 seeded empty-workspace runs.

## qwen2.5-coder:7b

- unique committed hashes: **14**
- highest gates: ['G4_partial_3', 'G4_partial_2', 'G4_partial_3', 'none', 'G1']

| Class | Count | % of taxonomy events |
| --- | ---: | ---: |
| FORMAT | 0 | 0.0% |
| SYNTAX | 0 | 0.0% |
| RUNTIME | 3 | 12.0% |
| GENERALITY | 0 | 0.0% |
| FEASIBILITY | 22 | 88.0% |
| OPTIMIZATION | 0 | 0.0% |
| NO_OP | 0 | 0.0% |

| Feasibility family (mentions) | Count |
| --- | ---: |
| BATTERY | 26 |
| WINDOW | 0 |
| CAPACITY | 0 |
| VISIT | 0 |
| DEPOT | 0 |

Role activity (algo_draft/agent tags): charging=22

## deepseek-coder:6.7b

- unique committed hashes: **12**
- highest gates: ['none', 'G1', 'G0', 'none', 'G0']

| Class | Count | % of taxonomy events |
| --- | ---: | ---: |
| FORMAT | 0 | 0.0% |
| SYNTAX | 0 | 0.0% |
| RUNTIME | 10 | 50.0% |
| GENERALITY | 0 | 0.0% |
| FEASIBILITY | 10 | 50.0% |
| OPTIMIZATION | 0 | 0.0% |
| NO_OP | 0 | 0.0% |

| Feasibility family (mentions) | Count |
| --- | ---: |
| BATTERY | 5 |
| WINDOW | 0 |
| CAPACITY | 0 |
| VISIT | 5 |
| DEPOT | 4 |

Role activity (algo_draft/agent tags): charging=4, routing=6

## codellama:7b

- unique committed hashes: **3**
- highest gates: ['G1', 'none', 'G3', 'G1', 'G1']

| Class | Count | % of taxonomy events |
| --- | ---: | ---: |
| FORMAT | 1 | 3.6% |
| SYNTAX | 1 | 3.6% |
| RUNTIME | 6 | 21.4% |
| GENERALITY | 3 | 10.7% |
| FEASIBILITY | 17 | 60.7% |
| OPTIMIZATION | 0 | 0.0% |
| NO_OP | 0 | 0.0% |

| Feasibility family (mentions) | Count |
| --- | ---: |
| BATTERY | 18 |
| WINDOW | 0 |
| CAPACITY | 0 |
| VISIT | 0 |
| DEPOT | 0 |

Role activity (algo_draft/agent tags): charging=17

## deepseek-coder-v2:16b

- unique committed hashes: **6**
- highest gates: ['G1', 'G1', 'G1', 'G1', 'none']

| Class | Count | % of taxonomy events |
| --- | ---: | ---: |
| FORMAT | 0 | 0.0% |
| SYNTAX | 0 | 0.0% |
| RUNTIME | 9 | 47.4% |
| GENERALITY | 4 | 21.1% |
| FEASIBILITY | 6 | 31.6% |
| OPTIMIZATION | 0 | 0.0% |
| NO_OP | 0 | 0.0% |

| Feasibility family (mentions) | Count |
| --- | ---: |
| BATTERY | 2 |
| WINDOW | 0 |
| CAPACITY | 0 |
| VISIT | 0 |
| DEPOT | 6 |

Role activity (algo_draft/agent tags): charging=6


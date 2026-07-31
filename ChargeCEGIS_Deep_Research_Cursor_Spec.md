# ChargeCEGIS — Cursor Redesign and Research Specification
## Making the EVRPTW + Small-LLM Paper Scientifically Unique

**Document purpose:**  
Refactor the current project into a minimal, paper-focused research system that tests whether small local coding LLMs can discover compact, verifiable, and transferable EVRPTW search policies better than equal-budget non-LLM program search.

**Primary solver:** deterministic ALNS  
**Primary benchmark:** Schneider EVRPTW  
**Primary model:** `qwen2.5-coder:3b`  
**Model comparison:** `qwen2.5-coder:1.5b`, `qwen2.5-coder:3b`, `qwen2.5-coder:7b`  
**Agent count:** exactly five  
**Generated object:** a compact typed policy, not arbitrary Python and not a complete solver

---

# 1. Research objective

The project must answer one central scientific question:

> Can small local coding LLMs discover compact policies for coupled routing-and-charging decisions in EVRPTW that generalize to unseen benchmark families and outperform typed genetic programming, random search, and handcrafted policies under equal numerical evaluation budgets?

The system must not be presented as a commercial software platform.

The paper is about:

- automatic heuristic discovery;
- small local LLMs;
- EVRPTW-specific reasoning;
- deterministic verification;
- counterexample-guided refinement;
- fair LLM-versus-non-LLM comparison;
- unseen-family generalization.

The paper is not about:

- creating many software layers;
- generating entire solvers;
- adding many loosely justified agents;
- unrestricted LLM code execution;
- building a generic routing service;
- claiming that an LLM directly solves EVRPTW.

---

# 2. Recommended title

## Main title

**Small-LLM Discovery of Verifiable Coupled Routing-and-Charging Policies for the Electric Vehicle Routing Problem with Time Windows**

## Method name

**ChargeCEGIS**

## Alternative title

**ChargeCEGIS: Counterexample-Guided Small-LLM Discovery of Coupled Route-and-Charging Policies for EVRPTW**

The first title is clearer for reviewers. Use “ChargeCEGIS” as the method name inside the paper.

---

# 3. One-paragraph system description

ChargeCEGIS is a five-stage agentic framework that uses small local coding LLMs to discover compact priority policies for coupled route-and-charging moves inside a deterministic EVRPTW ALNS solver. The LLM does not construct routes or calculate feasibility. Instead, the solver generates candidate customer-segment and charging-station modifications, while the generated policy ranks which moves should be attempted. Five sequential roles diagnose search failures, formulate a hypothesis, synthesize a typed policy, challenge it with counterexamples, and interpret measured results. All route propagation, battery calculations, charging reconstruction, time-window checking, and policy evaluation remain deterministic. The paper compares small LLMs with typed genetic programming, random search, and handcrafted policies on held-out Schneider benchmark families.

---

# 4. Why the paper can be unique

Recent work already covers:

- LLM-generated VRP operators;
- reflective heuristic evolution;
- generated LNS destroy and repair code;
- LLM evolution of HGS components;
- general program search with LLMs;
- multi-agent solver construction.

Therefore, the paper must not claim novelty from “using LLMs for VRP,” “using five agents,” “using reflection,” or “generating operators.”

The novelty must come from the combination of the following technical contributions.

## 4.1 Coupled routing-and-charging policy representation

The policy must score moves that jointly involve:

- customer segments;
- route insertion or exchange;
- charging-station removal;
- charging-station replacement;
- charging reconstruction;
- time-window consequences;
- battery-slack consequences.

This is EVRPTW-specific and must be central.

## 4.2 Typed policy language shared by all search methods

LLMs, genetic programming, random search, and handcrafted methods must all operate in the same typed policy space.

This gives:

- equal implementation freedom;
- interpretable policies;
- safer execution;
- fair comparison;
- structural complexity control;
- reproducible search.

## 4.3 Counterexample-guided policy refinement

A dedicated Counterexample Agent proposes challenge conditions.

Deterministic software then constructs or selects actual counterexamples and checks the candidate policy.

Examples:

- a move reduces charging distance but causes downstream lateness;
- a policy changes behavior under customer relabeling;
- a policy always selects the first candidate;
- a policy only works on clustered instances;
- a policy improves distance but increases vehicles;
- a policy ranks a move highly when no feasible charging alternative exists.

The policy receives at most one revision after counterexample feedback.

## 4.4 True permutation invariance

Accepted policies must behave consistently under equivalent relabelings of:

- customers;
- charging stations;
- route order.

The project must actually relabel the instance and solution, rerun feature generation, evaluate the policy, map actions back, and compare behavior.

## 4.5 Small-model efficiency study

The paper should investigate whether restrictive search and strong verification allow small local models to perform useful heuristic discovery.

Compare:

- 1.5B;
- 3B;
- 7B.

Report:

- valid policy rate;
- effective policy rate;
- held-out solver quality;
- latency;
- candidates per hour;
- memory;
- total search cost.

## 4.6 Equal-budget comparison against typed GP

This is essential.

The paper must test whether pretrained language knowledge helps beyond ordinary program search.

Compare:

- small-LLM search;
- typed genetic programming;
- random typed search;
- deterministic structured mutation;
- handcrafted policies.

Use the same:

- DSL;
- features;
- policy complexity;
- initial policies;
- number of evaluated candidates;
- solver budgets;
- development instances.

---

# 5. Keep ALNS

## Decision

Keep ALNS as the primary deterministic solver.

Do not replace it with HGS in the main method.

## Reasons

ALNS is a suitable scientific host because:

- destroy and repair decisions are exposed;
- charging reconstruction can remain deterministic;
- generated policies can be isolated;
- operator effects can be measured;
- handcrafted and generated policies can be compared in the same solver;
- the method remains understandable.

Do not claim that ALNS is the strongest possible EVRPTW solver.

Claim:

> ALNS provides a controlled host for automatic discovery of route-and-charging policies.

## Optional comparison

Use published Schneider results or a correctly reproduced classical baseline where objective definitions match.

Do not implement a full second solver unless required by reviewers.

---

# 6. Exactly five agents

The five roles must be scientifically distinct.

## Agent 1 — Diagnostic Analyst

### Input

- route-level diagnostics;
- battery-slack distributions;
- time-slack distributions;
- charging detours;
- move acceptance;
- move effectiveness;
- rejection reasons;
- search stagnation;
- prior candidate behavior.

### Output

```json
{
  "dominant_failure": "...",
  "supporting_metrics": ["..."],
  "alternative_explanations": ["..."],
  "uncertainty": 0.0,
  "missing_evidence": ["..."]
}
```

### Responsibility

Identify why the current solver or policy is weak.

### Prohibited

- code generation;
- route construction;
- claims unsupported by metrics.

---

## Agent 2 — Policy Scientist

### Input

- Analyst report;
- feature catalogue;
- current archive;
- known handcrafted policies.

### Output

```json
{
  "hypothesis": "...",
  "target_mechanism": "...",
  "required_features": ["..."],
  "expected_behavior": "...",
  "no_action_conditions": ["..."],
  "invariants": ["..."],
  "falsification_condition": "..."
}
```

### Responsibility

Turn one diagnosis into one falsifiable policy hypothesis.

### Prohibited

- proposing several unrelated systems;
- generating implementation code.

---

## Agent 3 — Policy Synthesizer

### Input

- Scientist hypothesis;
- DSL grammar;
- feature definitions;
- examples of valid compact policies;
- complexity limits.

### Output

A valid JSON policy AST only.

### Responsibility

Generate one compact typed priority policy.

### Prohibited

- Python;
- imports;
- loops;
- route IDs;
- customer IDs;
- station IDs;
- raw coordinates;
- arbitrary strings.

---

## Agent 4 — Counterexample Agent

### Input

- policy AST;
- hypothesis;
- known invariants;
- behavioral summary;
- feature catalogue.

### Output

```json
{
  "challenges": [
    {
      "type": "...",
      "target_failure": "...",
      "state_requirements": ["..."],
      "expected_invariant": "..."
    }
  ]
}
```

### Responsibility

Propose adversarial and boundary scenarios.

### Important

The Counterexample Agent does not verify correctness.

Deterministic code must create/select the states and execute the test.

---

## Agent 5 — Experimental Critic

### Input

- deterministic verification results;
- counterexamples;
- development performance;
- behavior metrics;
- policy complexity;
- comparison with parents and handcrafted policies.

### Output

```json
{
  "decision": "REJECT | RETAIN | REVISE_ONCE",
  "evidence": ["..."],
  "failure_class": "...",
  "revision_instruction": "...",
  "claim_limit": "..."
}
```

### Responsibility

Interpret evidence and allow at most one focused revision.

### Prohibited

- repeated open-ended revision;
- declaring correctness;
- overriding deterministic results.

---

# 7. Deterministic components are not agents

Keep these as ordinary modules:

- parser;
- route propagation;
- feasibility validator;
- charging reconstruction;
- move enumeration;
- feature extraction;
- policy interpreter;
- policy verifier;
- counterexample executor;
- ALNS;
- experiment runner;
- statistics;
- archive.

Do not call them agents in the paper.

---

# 8. Small LLM selection

## Primary model

```text
qwen2.5-coder:3b
```

Use it for the main method because it balances:

- coding ability;
- speed;
- memory;
- local deployment;
- number of candidates per hour.

## Model comparison

```text
qwen2.5-coder:1.5b
qwen2.5-coder:3b
qwen2.5-coder:7b
```

Use the same family to isolate the effect of scale.

## Ollama configuration

```yaml
ollama:
  num_ctx: 4096
  keep_alive: "20m"
  stream: false
  sequential_requests: true
```

## Temperatures

```yaml
temperatures:
  analyst: 0.10
  scientist: 0.45
  synthesizer: 0.20
  counterexample: 0.40
  critic: 0.10
```

## Reproducibility

Record:

- exact Ollama model tag;
- model digest;
- Ollama version;
- context length;
- temperature;
- generation seed where supported;
- prompt hash;
- response hash;
- latency;
- token counts where available.

---

# 9. Replace arbitrary generated Python with a typed DSL

This change is mandatory for the final paper path.

## 9.1 Policy function

The generated object represents:

\[
\pi(m, S, I) \rightarrow \mathbb{R}
\]

where the output is the priority of a deterministically enumerated move.

## 9.2 Allowed grammar

Arithmetic:

```text
add
sub
mul
safe_div
min
max
abs
neg
```

Comparisons:

```text
lt
le
gt
ge
```

Logic:

```text
and
or
not
```

Conditional:

```text
if
```

Terminals:

```text
normalized feature
bounded constant
```

## 9.3 Forbidden constructs

Do not allow:

- loops;
- recursion;
- imports;
- functions;
- list indexing;
- arbitrary attribute access;
- identifiers;
- random calls;
- I/O;
- hidden mutable state.

## 9.4 Complexity limits

```yaml
policy:
  max_nodes: 45
  max_depth: 6
  max_conditionals: 4
  max_constant_abs: 5.0
  require_feature_use: true
```

## 9.5 Example policy

```json
{
  "op": "if",
  "condition": {
    "op": "gt",
    "left": {"feature": "alternative_station_count"},
    "right": {"const": 0.0}
  },
  "then": {
    "op": "add",
    "args": [
      {
        "op": "mul",
        "args": [
          {"const": 1.6},
          {"feature": "charging_detour_reduction"}
        ]
      },
      {
        "op": "mul",
        "args": [
          {"const": 0.7},
          {"feature": "minimum_time_slack_after"}
        ]
      }
    ]
  },
  "else": {"const": -2.0}
}
```

---

# 10. Coupled move catalogue

The deterministic solver must enumerate a small fixed catalogue.

## Move A — Segment relocation with charging reconstruction

- remove a nonempty contiguous customer segment;
- remove charging visits that become redundant;
- insert the segment into another route or position;
- reconstruct charging deterministically.

## Move B — Route-tail exchange with charging reconstruction

- exchange customer tails between two routes;
- reconstruct charging on both routes.

## Move C — Station replacement

- replace an existing station with a distinct feasible alternative;
- recompute battery and schedule.

## Move D — Redundant station removal

- remove a station;
- retain only if the route remains feasible.

Do not let the LLM generate move execution code during the main study.

---

# 11. Required EVRPTW features

Every feature must be move-specific and mathematically correct.

```text
delta_distance_estimate
delta_charging_distance
delta_charging_time
delta_station_count
minimum_energy_slack_before
minimum_energy_slack_after
minimum_time_slack_before
minimum_time_slack_after
segment_distance_contribution
segment_customer_count
segment_demand
route_load_utilization
alternative_station_count
station_detour_contribution
station_time_contribution
customer_relatedness
estimated_repair_cost
historical_move_acceptance_rate
historical_move_improvement_rate
move_type_segment_relocation
move_type_tail_exchange
move_type_station_replacement
move_type_station_removal
```

Normalize features using statistics from development data only.

## Correct definitions

### Energy slack

For arc \((i,j)\):

\[
\text{energy\_slack}_{i,j}
=
b_i^{\text{departure}}
-
e_{i,j}.
\]

### Time slack

For node \(i\):

\[
\text{time\_slack}_i
=
l_i - \text{service\_start}_i.
\]

### Station detour contribution

For a station \(s\) between predecessor \(p\) and successor \(q\):

\[
d(p,s) + d(s,q) - d(p,q).
\]

### Charging time contribution

Use actual recharge duration implied by the locked benchmark charging model.

---

# 12. Counterfactual feedback

For every attempted move, store:

```text
feasible
rejection_reason
delta_vehicles
delta_distance
delta_charging_distance
delta_charging_time
delta_station_count
delta_minimum_energy_slack
delta_minimum_time_slack
route_assignment_changed
customer_sequence_changed
station_sequence_changed
accepted_by_alns
became_new_best
runtime
```

The Critic receives summaries such as:

> The policy selected moves that reduced charging detour, but 63% failed because downstream time slack was below zero after charging reconstruction.

The LLM must never receive only a scalar fitness.

---

# 13. Counterexample-guided loop

Use exactly one initial synthesis and at most one revision.

```text
ALNS diagnostics
→ Analyst
→ Scientist
→ Synthesizer
→ deterministic DSL verification
→ Counterexample Agent
→ deterministic counterexample execution
→ development evaluation
→ Critic
→ optional one revision
→ final evaluation
→ archive
```

## Counterexample categories

### Structural

- customer relabeling;
- station relabeling;
- route-order permutation;
- move-list permutation;
- equivalent feature-vector duplicates.

### Applicability

- no feasible station alternative;
- no removable segment;
- no charging stop;
- all routes have high energy slack;
- all candidate moves violate time windows.

### Behavioral

- constant policy;
- first-move bias;
- single-move-type collapse;
- ignoring all charging features;
- equivalent to a handcrafted policy;
- excessive no-action behavior.

### Optimization

- distance decreases but fleet size increases;
- station count decreases but lateness occurs;
- high action rate with low effective-change rate;
- gains only on one benchmark family;
- runtime overhead dominates gain.

---

# 14. True metamorphic testing

Implement actual relabel-and-rerun tests.

## Procedure

1. Copy the instance.
2. Permute customer IDs.
3. Permute station IDs.
4. Relabel the solution.
5. Recompute all candidate moves and features.
6. Evaluate the policy.
7. Map selected moves back.
8. Compare rankings or selected actions.

The test must fail when behavior changes for an equivalent state.

Do not use an identity transformation.

---

# 15. Correctness fixes before experiments

Fix the deterministic foundation first.

## Dataset

- discover exactly 92 Schneider instances;
- exclude `readme.txt`;
- validate 36 small and 56 large instances;
- use complete filename stems as IDs;
- remove or regenerate incorrect converted summaries.

## Feasibility

Enforce:

- every customer exactly once;
- load capacity;
- customer time windows;
- battery bounds;
- station constraints;
- depot return before depot due time;
- charging policy;
- valid start and terminal states.

## Charging

Lock one benchmark formulation.

For original Schneider full recharge:

- every charging stop must leave at full battery;
- reject partial recharge decisions;
- document charging rate and assumptions.

## Time budget

Check time limits:

- between ALNS iterations;
- before large move enumeration;
- during expensive reconstruction where feasible.

Record overshoot.

## Attribution

A failed LLM output must remain a failed LLM output.

Use separate labels:

```text
PURE_LLM_POLICY
LLM_HYPOTHESIS_TYPED_POLICY
GP_POLICY
RANDOM_POLICY
HANDCRAFTED_POLICY
```

Never credit deterministic fallback generation to the LLM.

---

# 16. Minimal codebase

Create branch:

```text
paper-minimal
```

Keep the old prototype in a separate archive or tag.

## Active tree

```text
chargecegis/
├── pyproject.toml
├── uv.lock
├── README.md
├── configs/
│   ├── solver.yaml
│   ├── models.yaml
│   └── experiments.yaml
├── data/
│   ├── schneider/
│   └── splits/
├── prompts/
│   ├── analyst.md
│   ├── scientist.md
│   ├── synthesizer.md
│   ├── counterexample.md
│   └── critic.md
├── src/chargecegis/
│   ├── data.py
│   ├── problem.py
│   ├── propagation.py
│   ├── feasibility.py
│   ├── charging.py
│   ├── construction.py
│   ├── alns.py
│   ├── moves.py
│   ├── features.py
│   ├── policy_dsl.py
│   ├── agents.py
│   ├── counterexamples.py
│   ├── search.py
│   ├── experiment.py
│   ├── statistics.py
│   └── plots.py
├── tests/
│   ├── test_data.py
│   ├── test_propagation.py
│   ├── test_feasibility.py
│   ├── test_charging.py
│   ├── test_alns_control.py
│   ├── test_policy_dsl.py
│   ├── test_features.py
│   ├── test_metamorphic.py
│   └── test_agents_mock.py
└── results/
```

Target:

- about 15 active source modules;
- no file per tiny schema;
- no milestone directories;
- no giant CLI hierarchy.

## Archive from active path

Archive:

- milestone-specific code;
- arbitrary generated Python sandbox;
- old operator APIs;
- complex orchestration state machines;
- duplicated schemas;
- unused benchmark adapters;
- software packaging code;
- dashboards;
- local `.venv`;
- caches;
- obsolete candidates;
- historical experiment wrappers.

---

# 17. Minimal policy search algorithm

## Initial archive

Start with:

1. zero policy;
2. charging-detour policy;
3. low-energy-slack policy;
4. low-time-slack policy;
5. combined handcrafted policy.

## Per discovery run

- generate 20 initial LLM policies;
- verify every policy;
- evaluate valid policies;
- select at most 5 promising policies for one revision;
- maintain a Pareto archive of at most 10 policies.

## Parent prompt context

Provide:

- one strong policy;
- one behaviorally diverse policy;
- one short failure summary;
- one counterexample;
- no full repository;
- no raw full instance.

## Archive fields

```text
policy_id
parent_ids
model
generation_seed
prompt_hash
policy_ast
policy_hash
verification
counterexamples
development_results
behavior_metrics
complexity
```

Use JSONL or SQLite.

---

# 18. Fair non-LLM baselines

All methods use the same DSL.

## Random typed search

Generate valid random ASTs under the same size limits.

## Typed genetic programming

Use:

- type-safe subtree mutation;
- type-safe subtree crossover;
- constant mutation;
- feature replacement;
- conditional insertion/removal.

## Structured deterministic mutation

Apply one controlled change:

- replace one feature;
- modify one constant;
- replace one operator;
- add or remove one condition.

## Handcrafted policies

At least:

- charging-detour first;
- low-energy-slack first;
- low-time-slack first;
- combined route-and-charge score.

## LLM ablations

- one-shot Synthesizer;
- Analyst + Scientist + Synthesizer;
- full system without Counterexample Agent;
- full system without Critic revision;
- full five-stage workflow.

---

# 19. Schneider benchmark protocol

Use the established Schneider EVRPTW collection.

## Data roles

### Small instances

Use 36 small instances for:

- parser correctness;
- feasibility tests;
- feature validation;
- early policy screening;
- counterexample execution.

### Large instances

Use 56 large instances for:

- validation;
- family-held-out final testing;
- solver-quality conclusions.

## Families

```text
C1
C2
R1
R2
RC1
RC2
```

## Six-fold family-held-out study

For each fold:

1. hold out one complete family;
2. use the other five for discovery and validation;
3. freeze the selected policy;
4. evaluate on all large instances in the held-out family;
5. do not expose test-family results to agents or selection.

This is stronger than a random instance split because it measures distribution transfer.

---

# 20. Evaluation budgets

## Discovery

For each model:

- 3 independent discovery seeds;
- 20 initial candidates per seed;
- at most 5 revised candidates per seed.

Initial total:

\[
3 \text{ models} \times 3 \text{ seeds} \times 20
= 180 \text{ LLM candidates}.
\]

GP, random search, and structured mutation must receive the same number of evaluated candidates.

## Solver evaluation

- primary budget: fixed ALNS iterations;
- same initial solution;
- same paired ALNS seeds;
- same RNG streams;
- same move catalogue;
- same charging reconstruction.

Use:

- minimum 5 ALNS seeds per held-out instance;
- 10 when computationally feasible.

## Control

Baseline and no-op must produce:

- identical objective;
- identical solution hash;
- identical trace hash where deterministic equivalence is expected.

---

# 21. Metrics

## Policy generation

- valid JSON rate;
- DSL parse rate;
- verification pass rate;
- counterexample pass rate;
- revision success;
- policy complexity;
- unique AST count.

## Behavior

- applicability;
- no-action rate;
- effective route change;
- station change;
- inert behavior;
- harmful behavior;
- move-type diversity;
- family coverage;
- similarity to handcrafted policies.

## Solver quality

Lexicographic order:

1. feasibility;
2. vehicles;
3. distance.

Also report:

- runtime;
- time to best;
- convergence;
- charging distance;
- charging time;
- station count;
- seed variance.

## Efficiency

- generation latency;
- candidates per hour;
- inference time;
- ALNS evaluation time;
- total discovery time;
- memory;
- GPU residency;
- tokens where available.

---

# 22. Statistics

Use the instance as the primary statistical unit.

Required:

- paired win/tie/loss;
- median difference;
- bootstrap 95% confidence intervals;
- Wilcoxon signed-rank test when appropriate;
- Holm correction;
- effect size:
  - Cliff’s delta; or
  - Vargha–Delaney \(A_{12}\).

For fleet count:

- fewer;
- equal;
- more vehicles.

For distance:

- compare only when fleet counts are equal.

Do not pool every seed as an independent sample.

---

# 23. Main research questions

## RQ1

Can small coding LLMs generate valid and semantically invariant EVRPTW priority policies?

## RQ2

Does counterexample-guided refinement improve validity, robustness, and held-out performance?

## RQ3

Do LLM-discovered policies outperform typed GP and random search under equal evaluation budgets?

## RQ4

How does model scale affect policy validity, behavioral novelty, solver quality, and inference cost?

## RQ5

Do discovered policies generalize across unseen Schneider families?

## RQ6

Which EVRPTW conditions benefit most:

- clustered geography;
- random geography;
- narrow horizons;
- wide horizons;
- tight energy;
- high charging detour?

---

# 24. Required ablations

Run only scientifically necessary ablations.

1. no Analyst;
2. no Scientist;
3. no Counterexample Agent;
4. no Critic revision;
5. one-shot Synthesizer;
6. no charging-specific features;
7. no permutation test;
8. unrestricted weighted linear policy only;
9. LLM versus GP;
10. 1.5B versus 3B versus 7B.

The most important ablations are:

- without Counterexample Agent;
- without Critic revision;
- LLM versus GP;
- without charging-specific features.

---

# 25. Required figures

1. System architecture.
2. Five-stage synthesis loop.
3. Candidate verification funnel.
4. Model-scale comparison.
5. LLM versus GP/random search under equal budget.
6. Held-out win/tie/loss by family.
7. Convergence curves.
8. Policy complexity versus performance Pareto plot.
9. Before/after route-and-charging case study.
10. Counterexample and Critic ablation.

Every figure must have:

- source CSV;
- generation script;
- caption;
- experiment IDs;
- configuration hash.

---

# 26. Required tables

1. Schneider data summary.
2. Model configuration.
3. Agent roles and outputs.
4. Policy DSL grammar.
5. Generation and verification rates.
6. LLM versus GP/random discovery results.
7. Held-out solver results.
8. Results by family.
9. Ablations.
10. Runtime and inference cost.
11. Selected policy expressions and interpretations.
12. Supported and unsupported claims.

---

# 27. Related-work positioning

The paper must state clearly:

## FunSearch

Borrow:

- fixed program skeleton;
- small evolvable function;
- evaluator-grounded search;
- interpretable program output.

Difference:

- EVRPTW;
- small local models;
- typed domain DSL;
- counterexample-guided revision;
- family-held-out transfer.

## ReEvo

Borrow:

- numerical feedback;
- reflective evolution;
- verbal guidance.

Difference:

- concrete deterministic counterexamples;
- typed policy space;
- EVRPTW coupled routing-and-charging actions.

## VRPAgent

Borrow:

- generated components inside a stable metaheuristic.

Difference:

- no arbitrary operator code;
- no complete route operators;
- explicit battery and charging coupling;
- shared DSL with GP.

## G-LNS

Borrow:

- destroy/repair coupling.

Difference:

- policy ranks pre-enumerated coupled EV moves;
- deterministic move execution;
- small models;
- counterexample verification.

## PyVRP+

Borrow:

- diagnosis, hypothesis, action, reflection.

Difference:

- EVRPTW;
- typed policy synthesis;
- five measured stages;
- counterexample role;
- small-model scaling.

## AlphaEvolve-style systems

Borrow:

- archive of evaluated programs;
- objective-based candidate selection;
- parent diversity.

Difference:

- minimal local implementation;
- no large ensemble;
- no industrial distributed search.

---

# 28. Claims policy

## Strong positive claim

Only make this claim if supported:

> Small coding LLMs combined with counterexample-guided verification discover compact coupled routing-and-charging policies that generalize to unseen EVRPTW families and outperform equal-budget typed program search.

## Moderate claim

> Counterexample-guided small-LLM search improves policy validity and behavioral usefulness, while optimization gains over typed GP are mixed.

## Negative but valuable claim

> Small LLMs generate interpretable and valid EVRPTW policies, but typed genetic programming matches or exceeds their optimization performance under equal evaluation budgets.

Do not repeatedly modify the method until the LLM wins.

---

# 29. What Cursor must do first

Before editing, Cursor must return:

1. current source-tree summary;
2. exact files to retain;
3. exact files to archive;
4. correctness issues mapped to source files;
5. proposed minimal directory tree;
6. DSL schema;
7. five agent schemas;
8. coupled move definitions;
9. feature definitions;
10. experiment-budget table;
11. estimate of active Python file count;
12. confirmation that no long experiments will run before approval.

After approval, Cursor should implement only:

1. deterministic correctness fixes;
2. minimal active tree;
3. policy DSL;
4. move features;
5. five agent prompts and schemas;
6. deterministic counterexample tests.

Then run focused tests and stop.

---

# 30. Implementation order

## Phase A — Freeze and simplify

- commit/tag current prototype;
- create `paper-minimal`;
- remove software-platform layers from active path.

## Phase B — Correct deterministic EVRPTW

- dataset;
- IDs;
- capacity;
- horizon;
- charging;
- slack;
- feasibility;
- no-op control.

## Phase C — Implement policy system

- DSL;
- interpreter;
- complexity;
- hashes;
- coupled moves;
- features.

## Phase D — Implement five roles

- prompts;
- structured outputs;
- one-revision loop.

## Phase E — Implement counterexamples

- relabeling;
- perturbation;
- invariants;
- equivalence checks.

## Phase F — Implement baselines

- GP;
- random;
- structured mutation;
- handcrafted.

## Phase G — Run experiments

- small correctness set;
- model comparison;
- six family-held-out folds;
- ablations;
- statistics.

## Phase H — Produce paper artifacts

- figures;
- tables;
- policy examples;
- costs;
- reproducibility package.

---

# 31. Final Cursor instruction

Stop treating the project as a software platform.

The final research implementation must be:

```text
correct deterministic EVRPTW ALNS
+ four fixed coupled move types
+ one typed priority-policy DSL
+ five sequential small-LLM roles
+ deterministic counterexample execution
+ equal-budget GP/random/handcrafted baselines
+ Schneider family-held-out evaluation
```

Do not add new agents, unrestricted code generation, additional solver frameworks, generic orchestration, dashboards, or milestone layers unless they directly answer one of the stated research questions.

The scientific value must come from:

- EVRPTW-specific coupling;
- counterexample-guided refinement;
- shared typed policy space;
- small-model efficiency;
- fair LLM-versus-GP comparison;
- held-out family generalization.

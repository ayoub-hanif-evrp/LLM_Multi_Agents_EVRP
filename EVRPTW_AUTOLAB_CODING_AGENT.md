# VoltForge (formerly drafted as EVRPTW-AutoLab) — Full Repository Reset and Five-Agent Autonomous Solver-Synthesis Specification

> **User-facing name:** VoltForge. AutoLab is a separate June 2026 autonomous-research-agent benchmark (arXiv:2606.05080). Do not use AutoLab as the paper title.

> **Audience:** coding agent / repository implementation agent  
> **Instruction type:** destructive migration + new-system implementation  
> **Priority:** this document supersedes the previous ChargeCEGIS architecture, scalar-policy DSL, fixed ALNS-host method, and old five-stage prompt pipeline.  
> **Goal:** replace the old project with a new multi-agent LLM system that **designs, writes, executes, debugs, evaluates, and evolves complete executable EVRPTW solver code**.

---

# 0. Read this first: the project is changing completely

The old research method must be removed from the working repository.

The new project is **NOT**:

- an LLM that solves an EVRPTW instance token-by-token;
- a fixed deterministic ALNS/HGS/GA solver with an LLM scoring formula on top;
- a scalar ranking-policy discovery system;
- a policy DSL search;
- an LLM that merely selects among prewritten destroy/repair operators;
- an Analyst → Scientist → Synthesizer → Counterexample → Critic pipeline;
- a system where a pre-existing deterministic optimizer remains the real solver.

The new project **IS**:

> A five-agent autonomous algorithm-development laboratory. The LLM agents collaboratively invent the EVRPTW optimization algorithm, generate/edit its Python code, execute candidate solvers on Schneider EVRPTW instances, inspect real experimental evidence, debug failures, evolve the solver architecture, preserve successful mechanisms, and finally export a reusable deterministic solver that requires zero LLM calls at deployment time.

The final scientific flow is:

```text
EVRPTW problem specification + benchmark contract
                     │
                     ▼
             FIVE LLM AGENTS
                     │
        design / code / test / evolve
                     │
                     ▼
         generated solver source code
                     │
                     ▼
          execute on development cases
                     │
                     ▼
       numerical evidence + failure traces
                     │
                     └───────────────┐
                                     │
                       agents revise code
                                     │
                                     ▼
                          better solver code
                                     │
                                    ...
                                     │
                                     ▼
                         FINAL GENERATED SOLVER
                                     │
                   ┌─────────────────┴─────────────────┐
                   ▼                                   ▼
             held-out instance                   new instance
                   │                                   │
                   ▼                                   ▼
                 CPU                                 CPU
                   │                                   │
                   ▼                                   ▼
            EVRPTW solution                     EVRPTW solution
```

**There must be no LLM call in final solver deployment.**

---

# 1. Non-negotiable design principles

## 1.1 The agents generate real solver code

The agents must be allowed to create and edit executable Python implementing optimization intelligence, including, but not limited to:

- construction algorithms;
- customer assignment strategies;
- routing heuristics;
- charging logic;
- route-repair logic;
- neighborhoods;
- local search;
- route elimination;
- genetic/evolutionary mechanisms;
- large-neighborhood mechanisms;
- tabu mechanisms;
- population management;
- crossover/mutation;
- acceptance logic;
- diversification/restarts;
- adaptive operator selection;
- hybrid algorithms;
- entirely new algorithm structures.

Do **not** force the agents to use ALNS, GA, HGS, Tabu, or any other predefined paradigm.

The Solver Architect may decide that a known paradigm is useful, combine several paradigms, or invent another structure.

## 1.2 No hidden deterministic optimizer under the agents

The fixed repository infrastructure may contain:

- Schneider instance loading;
- EVRPTW data structures;
- exact distance/travel/energy formulas;
- canonical post-run feasibility/objective evaluation;
- sandboxed code execution;
- experiment scheduling;
- time/memory limits;
- logging;
- result aggregation;
- model adapters;
- agent orchestration;
- code-version/lineage storage;
- benchmark split management.

It must **not** contain the proposed-method optimization algorithm.

Specifically, the fixed layer must not contain a prewritten production solver that performs:

- deterministic construction of the candidate routes for the agents;
- fixed ALNS search;
- fixed regret insertion as the main algorithm;
- fixed beam charging reconstruction as the main algorithm;
- automatic best insertion;
- fixed route elimination;
- fixed destroy/repair selection;
- a handcrafted operator schedule that the agents merely tune.

Basic problem-math utilities are allowed because they are not search intelligence.

## 1.3 Generated solver may be deterministic

The agents are creating code. That code may itself be deterministic, stochastic, heuristic, evolutionary, or hybrid.

The distinction is:

```text
BAD:
prewritten deterministic optimizer → LLM tunes one parameter/formula

GOOD:
LLM agents invent/write deterministic or stochastic optimization code → CPU executes it
```

## 1.4 Initial generation may be broad; subsequent evolution must be targeted

Generation 0 may create a complete solver from scratch.

After that, do not continuously regenerate the entire codebase. Maintain solver lineage and allow targeted code patches/replacements. This reduces model errors, token use, and causal ambiguity.

## 1.5 The final solver must be exportable and independent

The best solver must be exportable to a standalone directory/package with:

- no LLM dependency;
- no Ollama dependency;
- no synthesis-agent dependency;
- a stable CLI or Python entry point;
- deterministic/reproducible seed handling;
- ability to solve unseen Schneider-format instances.

---

# 2. Destructive migration: remove the old ChargeCEGIS method

Before deletion, if the repository is under Git, create a safety tag or branch **outside the new working architecture**:

```bash
git tag archive-before-evrptw-autolab
# or create an archive branch if preferred
```

This is only a recovery point. Do not preserve the old method inside the active source tree.

## 2.1 Delete the complete old source package

Delete:

```text
src/chargecegis/
```

This includes all old modules such as:

```text
agents.py
alns.py
charging.py
construction.py
counterexamples.py
data.py
experiment.py
feasibility.py
features.py
moves.py
plots.py
policy_dsl.py
problem.py
propagation.py
search.py
statistics.py
```

Do not leave compatibility wrappers that import or expose `chargecegis`.

Do not rename old ALNS/DSL code and pretend it is the new method.

The new code should be written as a clean package with a new namespace.

## 2.2 Delete all old prompts

Delete:

```text
prompts/analyst.md
prompts/scientist.md
prompts/synthesizer.md
prompts/counterexample.md
prompts/critic.md
```

Recreate `prompts/` using the new five-agent roles described below.

## 2.3 Delete old tests

Delete the existing ChargeCEGIS-specific tests, including:

```text
tests/test_agents.py
tests/test_alns_policy.py
tests/test_charging_moves.py
tests/test_counterexamples.py
tests/test_policy_dsl.py
```

Also remove stale `__pycache__`, `.pytest_cache`, `.mypy_cache`, and `.ruff_cache` artifacts from the repository working tree.

Rebuild tests for the new project from scratch.

## 2.4 Replace all old configuration

Delete or fully rewrite:

```text
configs/solver.yaml
configs/experiments.yaml
configs/models.yaml
```

No config should contain old concepts such as:

```text
RANDOM_RANKING
REFERENCE_DSL_RANKING
HANDCRAFTED_*_RANKING
ONE_SHOT_LLM
FULL_FIVE_STAGE_LLM
TYPED_GP
RANDOM_DSL
policy_search
policy.max_nodes
policy.max_depth
beam_width as the fixed proposed solver
fixed ALNS destroy fraction as the proposed method
```

## 2.5 Delete old results and manifests

The current `results/` directory contains results tied to the previous method. Delete it from the active project and recreate a clean result structure.

Remove old artifacts such as:

```text
best_policy_*.json
small_llm_gp_pilot.json
small_model_benchmark.json
feature_normalization.json
policy/ranking figures
old discovery-yield figures
old ranking W/T/L tables
old ALNS invocation logs
invalid_previous/
archived_preliminary_two_iteration/
```

If historical results must be preserved for the researcher, move them **outside the active repository** before deletion. Do not leave them in the active `results/` tree because they will be confused with the new method.

## 2.6 Rewrite project metadata

Replace the package name and all active branding.

Recommended package name:

```text
evrptw-autolab
```

Recommended Python package:

```text
evrptw_autolab
```

Update:

```text
pyproject.toml
README.md
CLI entry points
mypy package list
hatch package paths
all config comments
all tests
all docs
```

Suggested CLI:

```text
evrptw-autolab
```

No runtime code, test, configuration, README section, result schema, CLI entry point, or import should refer to the old project name.

## 2.7 Preserve only benchmark assets that are method-independent

Preserve the Schneider dataset itself:

```text
dataset/schneider/
```

A generic Schneider data contract may be preserved if it contains only dataset/problem-format information. Rename it if necessary to remove old project branding.

Do **not** preserve old optimization implementation code merely because it parses or evaluates routes. Reimplement a small, clean canonical problem layer for the new project so there is no accidental dependency on the old architecture.

---

# 3. New repository architecture

Create a clean package approximately like this:

```text
EVRPTW_AutoLab/
│
├── README.md
├── pyproject.toml
├── configs/
│   ├── models.yaml
│   ├── agents.yaml
│   ├── synthesis.yaml
│   ├── experiments.yaml
│   └── benchmark.yaml
│
├── prompts/
│   ├── solver_architect.md
│   ├── routing_engineer.md
│   ├── charging_engineer.md
│   ├── search_integration_engineer.md
│   └── test_evolution_critic.md
│
├── dataset/
│   └── schneider/
│       └── ... raw benchmark files ...
│
├── src/
│   └── evrptw_autolab/
│       ├── __init__.py
│       │
│       ├── problem/
│       │   ├── __init__.py
│       │   ├── types.py
│       │   ├── schneider.py
│       │   ├── physics.py
│       │   ├── evaluator.py
│       │   └── objective.py
│       │
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── ollama.py
│       │   ├── openai_compatible.py
│       │   ├── registry.py
│       │   └── usage.py
│       │
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── architect.py
│       │   ├── routing_engineer.py
│       │   ├── charging_engineer.py
│       │   ├── search_engineer.py
│       │   └── critic.py
│       │
│       ├── synthesis/
│       │   ├── __init__.py
│       │   ├── bootstrap.py
│       │   ├── proposal.py
│       │   ├── patching.py
│       │   ├── code_graph.py
│       │   ├── candidate.py
│       │   ├── integration.py
│       │   └── export.py
│       │
│       ├── sandbox/
│       │   ├── __init__.py
│       │   ├── static_scan.py
│       │   ├── runner.py
│       │   ├── limits.py
│       │   └── protocol.py
│       │
│       ├── evaluation/
│       │   ├── __init__.py
│       │   ├── fidelity.py
│       │   ├── runner.py
│       │   ├── metrics.py
│       │   ├── ranking.py
│       │   └── attribution.py
│       │
│       ├── memory/
│       │   ├── __init__.py
│       │   ├── archive.py
│       │   ├── lessons.py
│       │   └── retrieval.py
│       │
│       ├── orchestration/
│       │   ├── __init__.py
│       │   ├── cycle.py
│       │   ├── activation.py
│       │   ├── islands.py
│       │   └── state.py
│       │
│       ├── experiments/
│       │   ├── __init__.py
│       │   ├── model_benchmark.py
│       │   ├── team_ablation.py
│       │   ├── synthesis_campaign.py
│       │   ├── heldout.py
│       │   └── reports.py
│       │
│       └── cli.py
│
├── tests/
│   ├── test_problem_contract.py
│   ├── test_sandbox.py
│   ├── test_candidate_protocol.py
│   ├── test_patch_application.py
│   ├── test_code_graph.py
│   ├── test_agent_schemas.py
│   ├── test_evaluation_fidelity.py
│   ├── test_model_registry.py
│   ├── test_memory.py
│   └── test_end_to_end_smoke.py
│
├── workspace/
│   ├── candidates/
│   ├── elites/
│   ├── code_graph/
│   └── exports/
│
└── results/
    ├── runs/
    ├── campaigns/
    ├── model_comparison/
    ├── team_ablation/
    ├── heldout/
    ├── tables/
    └── figures/
```

This tree is a recommended organization, not an excuse to overengineer. Keep modules small and cohesive.

---

# 4. Fixed problem contract — NOT a solver

Create a new, minimal problem layer from scratch.

It may provide exact, deterministic problem mathematics so generated solvers do not hallucinate low-level arithmetic.

Required concepts:

```python
@dataclass(frozen=True)
class Node:
    id: str
    kind: Literal["depot", "customer", "station"]
    x: float
    y: float
    demand: float
    ready_time: float
    due_time: float
    service_time: float

@dataclass(frozen=True)
class VehicleSpec:
    capacity: float
    battery_capacity: float
    consumption_rate: float
    velocity: float

@dataclass(frozen=True)
class EVRPTWInstance:
    instance_id: str
    nodes: tuple[Node, ...]
    vehicle: VehicleSpec
    depot_id: str
```

The exact Schneider interpretation must be covered by tests.

The fixed problem layer may expose numerical utilities such as:

```python
distance(i, j)
travel_time(i, j)
energy_required(i, j)
propagate_route(route)
evaluate_solution(solution)
```

These functions must be purely computational. They must never select a customer, station, route, move, neighborhood, or search strategy.

The canonical evaluator must independently report at least:

```text
parse/format validity
all customers served exactly once
unserved customers
duplicate customers
capacity violations
time-window violations
battery violations
invalid charging behavior
vehicle count
total distance
charging visits
runtime
solver crash/timeout
```

Primary objective remains lexicographic unless the benchmark contract states otherwise:

```text
1. feasibility
2. vehicle count
3. distance
```

Do not hide infeasibility inside a weighted score when reporting final scientific results.

---

# 5. Generated solver contract

Every generated candidate solver must implement one stable external interface.

Recommended:

```python
def solve(instance, seed: int, time_limit_s: float):
    """Return a candidate EVRPTW solution."""
```

The returned object should follow a small serializable contract, for example:

```python
@dataclass
class CandidateSolution:
    routes: list[list[str]]
    metadata: dict[str, Any]
```

The generated solver may create any internal architecture it wants.

It can generate multiple files.

It may use allowed dependencies such as:

```text
Python standard library
numpy
```

Add other dependencies only deliberately and record them in the solver manifest.

Generated solver code must **not** call the LLM backend at runtime.

Generated solver code must **not** call a hidden classical baseline solver from the repository.

Generated solver code may call the fixed problem-math API because this only supplies exact calculations, not optimization decisions.

---

# 6. Five-agent architecture

Implement exactly five logical roles for the main system. They may share the same physical model backend.

A logical agent means a distinct:

- system prompt;
- role contract;
- structured output schema;
- context selection policy;
- memory view;
- code ownership emphasis;
- activation rule.

Do not implement them as five generic prompts saying approximately the same thing.

## Agent 1 — Solver Architect & Theorist

### Mission

Own the high-level solver hypothesis and code architecture.

### Responsibilities

- read current elite solver summaries and experiment traces;
- determine the main current failure mechanism;
- decide whether to improve routing, charging, search integration, or overall architecture;
- allocate the current LLM/evaluation budget;
- design Generation-0 solver architecture from scratch;
- propose architectural changes when evidence supports them;
- decide whether a solver island should be retained, merged, or abandoned;
- produce clear implementation tasks for specialist agents;
- prevent random uncontrolled code churn.

### Generation-0 freedom

The Architect may propose:

- ALNS;
- GA;
- memetic search;
- Tabu;
- hybrid genetic/local search;
- decomposition;
- multi-start local search;
- custom population search;
- another design.

Never force a specific paradigm in the Architect prompt.

### Output schema

At minimum:

```json
{
  "hypothesis": "...",
  "target": "BOOTSTRAP|ROUTING|CHARGING|SEARCH|ARCHITECTURE|TEST_ONLY",
  "evidence": ["..."],
  "agents_to_activate": ["routing", "charging", "search", "critic"],
  "files_or_components": ["..."],
  "success_criteria": ["..."],
  "budget": {
    "max_proposals": 2,
    "max_evaluation_fidelity": "F2"
  }
}
```

## Agent 2 — Routing Algorithm Engineer

### Mission

Invent and implement customer-routing optimization mechanisms.

### Responsibilities

May generate/edit code involving:

- initial routing construction;
- customer assignment;
- route sequencing;
- route elimination;
- segment/tail relocation;
- route exchange;
- crossovers;
- routing mutations;
- time-window-aware customer ordering;
- vehicle-count reduction;
- distance minimization;
- route-level neighborhoods;
- routing-specific data structures;
- routing-specific local search;
- route reconstruction.

This agent must not be constrained to a fixed old move library.

Its proposals should be executable code changes with a mechanism hypothesis.

## Agent 3 — Charging & Constraint Algorithm Engineer

### Mission

Invent and implement the EV-specific algorithmic mechanisms.

### Responsibilities

May generate/edit code involving:

- charging-station insertion/removal/replacement;
- energy-feasible route reconstruction;
- charging-aware customer sequencing;
- station dependency tracking;
- energy-critical arc detection;
- battery reserve logic;
- full-recharge Schneider policy handling;
- charging detour reduction;
- charging-induced time-window effects;
- joint routing/charging repair;
- energy-aware neighborhood logic;
- charging-specific local search;
- anticipatory charging decisions.

This role must have substantive code ownership. Do not reduce it to a reviewer of the Routing Engineer.

## Agent 4 — Search Strategy & Integration Engineer

### Mission

Turn candidate routing/charging mechanisms into an effective complete optimization algorithm.

### Responsibilities

May generate/edit:

- main optimization loop;
- operator scheduling;
- acceptance rules;
- adaptive control;
- population selection;
- diversity mechanisms;
- restart mechanisms;
- stagnation logic;
- portfolio selection;
- crossover/mutation scheduling;
- route/charging operator integration;
- search budgets;
- solver topology;
- multi-start strategy;
- adaptive strategy selection.

This agent should be allowed to replace the global search paradigm when the evidence justifies it.

## Agent 5 — Adversarial Test & Evolution Critic

### Mission

Find bugs, expose algorithmic weaknesses, interpret real numerical evidence, and assign evolutionary credit.

### Responsibilities

- generate targeted unit tests for generated solver code;
- generate adversarial synthetic EVRPTW cases;
- inspect crashes/timeouts;
- inspect infeasibility patterns;
- detect accidental benchmark leakage;
- detect overfitting to instance IDs/family names;
- diagnose performance regressions;
- compare child vs parent under identical budgets;
- recommend RETAIN / REVISE / REVERT / ABANDON;
- write one concise mechanism-level lesson into persistent memory;
- attribute improvement to changed code components where possible.

The Critic must see **actual executed results**, not just code descriptions.

### Output schema

```json
{
  "decision": "RETAIN|REVISE|REVERT|ABANDON",
  "primary_cause": "...",
  "evidence": ["..."],
  "credited_components": ["..."],
  "blamed_components": ["..."],
  "next_target": "ROUTING|CHARGING|SEARCH|ARCHITECTURE|NONE",
  "lesson": "one compact reusable scientific lesson"
}
```

---

# 7. Adaptive agent activation — do NOT call all five on every cycle

The framework has five agents, but agent activation must be gated by the current research target.

Examples:

```text
Charging failures high, routing strong
→ Architect + Charging Engineer + Critic
→ freeze routing/search code unless integration is required
```

```text
Search stagnation high, solution components feasible
→ Architect + Search Engineer + Critic
```

```text
Generation 0
→ all relevant agents may collaborate to create complete solver
```

```text
Compile failure caused by one module
→ owning engineer + Critic only
```

This is important for token efficiency and for causal attribution.

The orchestration state must record which roles were activated and why.

---

# 8. Initial solver synthesis

## 8.1 Generation 0 must be genuinely agent-generated

There must not be a hidden prewritten EVRPTW solver that becomes `solver_v0`.

Bootstrap procedure:

1. Feed the Architect:
   - EVRPTW problem specification;
   - generated-solver interface;
   - allowed dependencies;
   - runtime constraints;
   - benchmark split description without held-out solutions;
   - minimal problem API documentation.
2. Architect proposes a solver architecture.
3. Routing Engineer writes routing components.
4. Charging Engineer writes charging/constraint components.
5. Search Engineer integrates them into an executable algorithm.
6. Critic/Test agent writes tests and challenges.
7. Execute in sandbox.
8. Fix compile/runtime/feasibility defects through agent patches.
9. Save the first viable solver as an ancestor in the code graph.

## 8.2 Optional solver islands

Support 2–3 independent Generation-0 solver islands to preserve architectural diversity.

For example:

```text
Island A ← independent architecture proposal
Island B ← independent architecture proposal
Island C ← independent architecture proposal
```

Do not manually prescribe which paradigm each island must use.

Each island has its own lineage and elites.

Start with one island for the MVP; enable three-island campaigns after the end-to-end pipeline is stable.

---

# 9. Code proposal and patch protocol

Agents must output machine-parseable proposals.

Do not rely on scraping arbitrary Markdown code fences as the only protocol.

Recommended schema:

```json
{
  "proposal_id": "...",
  "role": "routing_engineer",
  "parent_solver_id": "...",
  "hypothesis": "...",
  "change_type": "CREATE|REPLACE_FILE|PATCH|DELETE_FILE|ARCHITECTURE",
  "files": [
    {
      "path": "solver/routing.py",
      "operation": "replace",
      "content": "... full Python source ..."
    }
  ],
  "expected_effect": {
    "feasibility": "...",
    "vehicles": "...",
    "distance": "...",
    "runtime": "..."
  },
  "requested_tests": ["..."]
}
```

For MVP, prefer **whole-file replacement for small generated modules** because it is easier to validate robustly than brittle line-number patches.

Later add unified-diff patches for large files.

Every candidate must have:

```text
solver_id
parent_solver_id
code_hash
author_role
model_id
prompt_hash
changed_files
hypothesis
creation timestamp
```

---

# 10. Solver code graph and lineage

Do not keep only `best_solver.py`.

Maintain a directed acyclic graph of solver evolution:

```text
S000
 ├── S001 routing patch R1
 │    ├── S004 charging patch C3
 │    └── S005 search patch A2
 └── S002 architecture alternative
      └── S006 ...
```

A node stores:

```json
{
  "solver_id": "S004",
  "parent": "S001",
  "code_hash": "...",
  "agent_role": "charging_engineer",
  "model": "...",
  "hypothesis": "...",
  "patch_id": "C3",
  "evaluation_summary": {...},
  "status": "ELITE|ARCHIVED|FAILED|REJECTED"
}
```

This allows:

- rollback;
- causal comparison;
- component credit;
- reproducibility;
- later analysis of how the solver was discovered.

---

# 11. Sandboxed execution of generated code

Generated code is untrusted.

Implement a strict execution layer.

## 11.1 Static checks before execution

At minimum:

- parse with `ast`;
- reject syntax errors;
- reject obviously dangerous imports/calls;
- reject network access;
- reject process spawning;
- reject shell execution;
- reject arbitrary filesystem traversal;
- reject environment-secret access;
- reject dynamic package installation;
- reject code that imports the experiment evaluator to read hidden answers;
- reject hard-coded held-out instance names/solutions.

Examples of disallowed capabilities unless explicitly sandboxed:

```text
subprocess
socket
requests/http clients
os.system
shutil destructive filesystem use
pip installation
reading arbitrary parent directories
```

## 11.2 Runtime limits

Each run must have:

```text
wall-clock timeout
process termination
memory cap where practical
captured stdout/stderr
seed
working-directory isolation
no network
```

Use `psutil` for cross-platform monitoring if needed.

Docker may be supported as an optional stronger sandbox, but the default pipeline should not require Docker to run basic experiments.

## 11.3 No benchmark cheating

Generated code must not be allowed to:

- inspect held-out result files;
- inspect BKS tables during optimization;
- branch on exact held-out instance IDs to emit hard-coded routes;
- load previous solutions as answers unless the experiment explicitly studies warm-start transfer.

The Critic should include leakage tests.

---

# 12. Multi-fidelity evaluation to control cost

Solver execution, not LLM generation, may become the dominant cost. Use staged evaluation.

## F0 — code validity

Every proposal:

```text
AST/static safety check
import check
compile check
unit tests
solver-interface check
```

Fail fast. No benchmark execution if F0 fails.

## F1 — tiny smoke evaluation

Use a very small fixed development subset, e.g. representative 5-customer instances.

Goals:

```text
runs without crash
returns valid schema
can produce at least some feasible solutions
obvious runtime sanity
```

## F2 — small Schneider development

Use 5/10/15-customer development cases excluding held-out-family information.

Use multiple families and at least two seeds for stochastic candidates when practical.

This is the main rapid evolutionary fitness layer.

## F3 — selected large representatives

Use a small fixed set of 100-customer instances covering non-held-out families.

Only candidates that pass F2 should reach F3.

## F4 — development confirmation

Run the strongest elites on the larger development suite with more seeds and a standardized runtime budget.

## FINAL — untouched held-out evaluation

The final held-out family must not influence:

- generation;
- prompts;
- code selection;
- architecture choice;
- memory;
- controller logic;
- model selection.

Recommended existing split policy:

```text
RC2 = final held-out family
```

If six-fold family cross-validation is later performed, implement it as a separate expensive final campaign, not as routine discovery feedback.

---

# 13. Candidate ranking and objective

The canonical evaluator must rank candidates lexicographically:

```text
1. solver correctness / no crash
2. feasibility success rate
3. unserved/violation severity if infeasible
4. vehicle count
5. distance at equal vehicle count
6. runtime / computational cost as secondary analysis
```

Do not let a very short but infeasible solver outrank a feasible solver.

For stochastic algorithms, compare using matched instance/seed/time budgets.

Keep raw per-instance results. Never store only aggregate scores.

---

# 14. Experimental traces sent back to agents

Do not dump huge raw logs into prompts.

Create concise machine-generated diagnostics containing information such as:

```text
compile/runtime status
feasible instance rate
mean/median vehicle count
mean distance conditional on equal vehicle count
worst families
best families
runtime distribution
common feasibility violations
battery-failure locations/statistics
time-window failure statistics
unserved-customer statistics
improvement trajectory
stagnation indicators
operator/function profiling if available
parent-vs-child matched deltas
```

Agent 5 may request a bounded number of additional diagnostic runs when needed.

---

# 15. Persistent research memory

Implement two levels of memory.

## 15.1 Full archive

Machine-only record of everything:

```text
all prompts
all responses
all code proposals
all code hashes
all run results
all seeds
all crashes
all tests
all model usage/tokens
all parent-child links
```

Do not inject the full archive into LLM context.

## 15.2 Mechanism memory

Compact validated lessons generated by the Critic.

JSONL example:

```json
{
  "lesson_id": "M027",
  "solver_lineage": "S031->S044",
  "problem": "route elimination frequently creates downstream energy repair failures",
  "mechanism": "preserve station dependency information during customer reassignment",
  "evidence": {
    "families_helped": ["C1", "RC1"],
    "families_hurt": ["R1"],
    "fidelity": "F3"
  },
  "lesson": "Route compression works better when charging dependencies are retained and station replacement considers downstream time slack."
}
```

The retrieval layer should select a small number of relevant lessons based on the current failure target.

Do not add a sixth "memory agent".

---

# 16. Multi-model support: mandatory

The new framework must be model-agnostic and support comparison of **at least 4 models and preferably 5 models**.

Do not hard-code one Qwen model in agent classes.

Every agent accepts a `model_profile` resolved through a central model registry.

## 16.1 Required backend abstraction

Implement at least:

```text
Ollama backend
OpenAI-compatible HTTP backend
```

The rest of the system must not care which provider generated the response.

A model profile should include:

```yaml
id: qwen25_coder_3b
provider: ollama
model: qwen2.5-coder:3b
timeout_s: 300
num_ctx: 8192
temperature_defaults:
  architect: 0.35
  routing: 0.25
  charging: 0.25
  search: 0.25
  critic: 0.10
```

## 16.2 Recommended initial five-model comparison set

Make this configurable. Suggested workstation-oriented profiles:

```text
1. qwen2.5-coder:1.5b
2. qwen2.5-coder:3b
3. qwen2.5-coder:7b
4. llama3.2:3b
5. phi4-mini:3.8b
```

These names are defaults, not assumptions. At startup, query the local Ollama model list.

If a configured model is unavailable:

```text
mark it SKIPPED_NOT_INSTALLED
print the exact missing model name
do not silently substitute another model
```

Also support optional stronger profiles such as Qwen3-Coder when hardware permits, but do not make a large model mandatory for the core experiment.

## 16.3 Main model comparison must use homogeneous teams

For scientific fairness, the primary LLM comparison should run:

```text
Team(model_1): model_1 used for all 5 roles
Team(model_2): model_2 used for all 5 roles
Team(model_3): model_3 used for all 5 roles
Team(model_4): model_4 used for all 5 roles
Team(model_5): model_5 used for all 5 roles
```

Keep identical:

```text
prompts
agent roles
maximum LLM calls
maximum tokens/context
solver evaluation budget
benchmark split
seeds
wall-clock solver budgets
initial problem information
```

This answers:

> Which LLM is best at autonomous EVRPTW solver synthesis under the same five-agent architecture?

Do not compare models using different roles in the main model benchmark.

## 16.4 Optional heterogeneous-team experiment

After the homogeneous comparison, optionally study a mixed team, e.g.:

```text
Architect = strongest reasoning/coding model
Routing = strongest routing-code model
Charging = strongest EV-constraint model
Search = strongest algorithm-integration model
Critic = strongest low-temperature diagnosis model
```

This is a secondary experiment because model-role assignment creates confounding.

## 16.5 Record usage

Per LLM call record:

```text
model id
provider
role
prompt tokens if available
completion tokens if available
latency
retry count
parse validity
code validity
```

Per campaign report:

```text
total LLM calls
total tokens
total LLM wall time
total solver evaluation time
valid-code yield
F1 pass rate
F2 effective-candidate rate
best final solver quality
```

---

# 17. Four-agent vs five-agent comparison: mandatory ablation support

The system must support both five-agent and four-agent configurations.

## 17.1 Five-agent main system

```text
1 Architect/Theorist
2 Routing Engineer
3 Charging Engineer
4 Search/Integration Engineer
5 Test/Evolution Critic
```

## 17.2 Four-agent reduced system

Recommended four-agent ablation:

```text
1 Solver Architect + Search/Integration Engineer (merged)
2 Routing Engineer
3 Charging Engineer
4 Test/Evolution Critic
```

This tests whether separating global architecture from search integration adds value.

Do not change the routing/charging specialization in this ablation.

## 17.3 Additional optional ablations

Support configurations such as:

```text
No dedicated Charging Engineer
No Critic/memory
No Architect gating (all roles run each cycle)
Monolithic single-agent solver designer
Three-agent reduced team
```

For paper-quality comparisons, enforce matched LLM-call/token and solver-evaluation budgets as closely as possible.

---

# 18. Suggested new configuration files

## `configs/models.yaml`

Example structure:

```yaml
provider_defaults:
  ollama:
    host: http://localhost:11434
    timeout_s: 300
    keep_alive: 20m

models:
  qwen25_coder_15b:
    enabled: true
    provider: ollama
    model: qwen2.5-coder:1.5b
    num_ctx: 8192

  qwen25_coder_3b:
    enabled: true
    provider: ollama
    model: qwen2.5-coder:3b
    num_ctx: 8192

  qwen25_coder_7b:
    enabled: true
    provider: ollama
    model: qwen2.5-coder:7b
    num_ctx: 8192

  llama32_3b:
    enabled: true
    provider: ollama
    model: llama3.2:3b
    num_ctx: 8192

  phi4_mini:
    enabled: true
    provider: ollama
    model: phi4-mini:3.8b
    num_ctx: 8192

optional_models:
  qwen3_coder:
    enabled: false
    provider: ollama
    model: qwen3-coder:30b
    note: enable only if hardware can run it reliably
```

Do not store machine-specific model digests as mandatory config. Record digests dynamically in experiment manifests when available.

## `configs/agents.yaml`

```yaml
team:
  mode: five_agent

roles:
  architect:
    prompt: prompts/solver_architect.md
    temperature: 0.35
    max_retries: 1

  routing:
    prompt: prompts/routing_engineer.md
    temperature: 0.25
    max_retries: 1

  charging:
    prompt: prompts/charging_engineer.md
    temperature: 0.25
    max_retries: 1

  search:
    prompt: prompts/search_integration_engineer.md
    temperature: 0.25
    max_retries: 1

  critic:
    prompt: prompts/test_evolution_critic.md
    temperature: 0.10
    max_retries: 1
```

## `configs/synthesis.yaml`

```yaml
bootstrap:
  islands: 1
  max_compile_repair_rounds: 3

cycle:
  max_role_proposals: 2
  gated_activation: true
  max_cycles: 30

lineage:
  max_elites_per_island: 3
  archive_all_valid_candidates: true

memory:
  max_lessons_in_prompt: 5
  max_lessons_total: 100
```

## `configs/experiments.yaml`

```yaml
data_root: dataset/schneider/raw_instances
held_out_family: RC2

fidelity:
  F1:
    customer_sizes: [5]
    seeds: [0]
  F2:
    customer_sizes: [5, 10, 15]
    seeds: [0, 1]
  F3:
    large_representatives_per_family: 1
    seeds: [0]
  F4:
    seeds: [0, 1, 2]

model_comparison:
  homogeneous_team: true
  model_ids:
    - qwen25_coder_15b
    - qwen25_coder_3b
    - qwen25_coder_7b
    - llama32_3b
    - phi4_mini

team_ablation:
  modes:
    - five_agent
    - four_agent_merged_architect_search
```

Exact instance lists should be generated deterministically and saved in a split manifest.

---

# 19. Prompts: required content

Create five new prompt files.

Every prompt must contain:

1. role identity;
2. exact code ownership/responsibility;
3. allowed input evidence;
4. solver interface contract;
5. prohibited behavior;
6. structured output schema;
7. requirement to make one coherent change/hypothesis at a time;
8. requirement to preserve working mechanisms unless evidence justifies removal;
9. requirement not to hard-code benchmark answers;
10. requirement to reason from empirical traces and relevant memory.

Do not ask agents to reveal chain-of-thought. Request concise design rationale/hypothesis fields only.

## Architect prompt emphasis

```text
You are free to invent the solver architecture.
Do not assume ALNS.
Do not rewrite working components without evidence.
Choose the smallest high-value research target for the current cycle.
```

## Routing prompt emphasis

```text
You own executable routing logic.
Generate real Python code changes, not a scoring formula.
Use exact problem utilities for arithmetic.
```

## Charging prompt emphasis

```text
You own executable EV-specific logic.
Treat routing, energy, stations, and time windows as coupled.
Generate actual algorithms/code, not commentary.
```

## Search prompt emphasis

```text
You own global search behavior and integration.
You may create, replace, or hybridize search paradigms when evidence supports it.
```

## Critic prompt emphasis

```text
You see executed evidence.
Find bugs and overfitting.
Do not praise code without numerical support.
Assign a decision and exactly one reusable mechanism lesson.
```

---

# 20. Research cycle

Implement the default cycle as:

```text
0. Current elite(s) exist

1. Evaluate current elite at required fidelity

2. Architect reads:
   - elite code summary
   - matched performance
   - failure diagnostics
   - relevant mechanism memory

3. Architect selects one research target and activates only required roles

4. Active code-generating agent(s) produce 1–2 candidate code changes

5. Static scanner / compile / unit tests
   - invalid → bounded repair attempt
   - still invalid → reject cheaply

6. F1 evaluation
   - poor/invalid → archive/reject

7. F2 evaluation for survivors

8. F3 only for strong candidates

9. Critic compares child to parent using matched budgets

10. Decision:
    RETAIN / REVISE / REVERT / ABANDON

11. Save:
    - code graph node
    - evaluation record
    - model usage
    - one mechanism lesson

12. Continue next cycle
```

Do not generate 60 unrelated candidates with no continuity.

---

# 21. Credit assignment

At minimum, a child is evaluated against its direct parent using the same:

```text
instances
seeds
time limits
hardware context
objective
```

When several components change together, support targeted counterfactual evaluation when affordable.

Example:

```text
Parent S10
Routing patch R3
Charging patch C5
Combined R3+C5
```

Evaluate, when needed:

```text
S10
S10+R3
S10+C5
S10+R3+C5
```

This helps distinguish:

```text
routing main effect
charging main effect
routing×charging interaction
```

Do **not** run a full factorial for every trivial patch. Use staged attribution only for promising or ambiguous changes.

The Critic may request the extra counterfactual only when it is scientifically useful.

---

# 22. Model-comparison experiment design

Implement a reproducible command such as:

```bash
evrptw-autolab benchmark-models --config configs/experiments.yaml
```

For each model:

1. initialize the same blank/generated-solver starting contract;
2. use the same benchmark split;
3. use the same role prompts;
4. use the same five-agent architecture;
5. use the same maximum discovery cycles;
6. use the same proposal limit per cycle;
7. use the same solver evaluation fidelity budget;
8. use the same LLM-call budget where practical;
9. use the same seeds;
10. export that model team's best discovered solver.

Report at least:

```text
model
successful solver bootstrap rate
compile-valid code proposal rate
runtime-valid proposal rate
F1 pass rate
F2 effective improvement rate
number of elite replacements
best feasibility rate
best vehicle count
best distance at equal fleet
solver runtime
LLM calls
LLM tokens
LLM generation time
solver evaluation time
final held-out performance
```

Do not use the final held-out family to select the winning model.

---

# 23. Team-size comparison

Implement:

```bash
evrptw-autolab benchmark-teams --modes five_agent four_agent_merged_architect_search
```

Use the same model for both team structures in a given comparison.

Control:

```text
total LLM-call budget
total evaluation budget
discovery cycles
benchmark split
seeds
```

The four-agent configuration merges only Architect + Search/Integration.

This lets the paper test:

> Does a distinct global Search/Integration Engineer improve autonomous EVRPTW solver synthesis beyond a four-agent team?

---

# 24. External baselines

The new proposed system must not depend on a classical baseline solver.

However, paper evaluation may compare the final generated solver against external/reference methods.

If baseline implementations are added later, isolate them under:

```text
baselines/
```

Rules:

- baseline code is never imported by generated solvers;
- baseline solutions are never shown to agents during discovery;
- baselines are used only for reporting/reference;
- clearly label unequal time/hardware budgets.

Known Schneider best-known values may be stored in an evaluation-only resource inaccessible to generated solver processes and discovery prompts.

---

# 25. Reproducibility requirements

Every campaign must write a manifest containing:

```text
git/source hash
Python version
OS
CPU/GPU/RAM if detectable
dataset split hash
model names
detected model digests when available
agent prompt hashes
all config hashes
random seeds
solver time limits
LLM budgets
candidate code hashes
final solver hash
```

Every generated solver must be reproducible from its lineage or stored full source snapshot.

Do not rely only on chat transcripts to reconstruct a solver.

---

# 26. Results schema

Use machine-readable JSONL/CSV or Parquet tables.

Suggested tables:

## `solver_runs`

```text
campaign_id
solver_id
parent_solver_id
model_id
team_mode
instance_id
family
customer_count
seed
fidelity
status
feasible
vehicles
distance
capacity_violations
time_violations
battery_violations
unserved
runtime_s
code_hash
```

## `llm_calls`

```text
campaign_id
cycle
role
model_id
proposal_id
prompt_hash
latency_s
prompt_tokens
completion_tokens
parse_valid
code_compile_valid
```

## `solver_lineage`

```text
solver_id
parent_solver_id
role
model_id
hypothesis
changed_files
patch_id
status
```

## `mechanism_memory`

```text
lesson_id
cycle
problem
mechanism
evidence
lesson
```

---

# 27. CLI requirements

Implement a coherent CLI. Suggested commands:

```bash
# Verify dataset and problem contract
evrptw-autolab validate-data

# Check available LLM models/backends
evrptw-autolab models list

# Bootstrap one solver from scratch
evrptw-autolab bootstrap --model qwen25_coder_3b --team five_agent

# Run one research/evolution campaign
evrptw-autolab discover --model qwen25_coder_3b --cycles 20

# Resume a campaign
evrptw-autolab resume <campaign_id>

# Evaluate one generated solver
evrptw-autolab evaluate <solver_id> --fidelity F3

# Compare LLMs
evrptw-autolab benchmark-models

# Compare 5-agent vs 4-agent teams
evrptw-autolab benchmark-teams

# Export final solver
evrptw-autolab export <solver_id> --output workspace/exports/final_solver

# Final held-out evaluation
evrptw-autolab heldout <solver_id>
```

Do not expose the held-out command casually during active discovery; require explicit final-evaluation mode and log its use.

---

# 28. Testing requirements

Before any real LLM campaign, all infrastructure tests must pass.

Required test groups:

## Problem contract

- Schneider parser correctness;
- distance formula;
- travel time;
- energy;
- full-recharge policy interpretation;
- time-window propagation;
- capacity;
- canonical solution evaluation.

## Sandbox

- rejects forbidden imports;
- kills infinite loop by timeout;
- captures exceptions;
- isolates working directory;
- blocks network/process spawning where supported;
- does not leak held-out files.

## Proposal handling

- valid agent JSON parses;
- invalid schema rejects cleanly;
- file replacement works;
- patch lineage is deterministic;
- code hash changes when code changes;
- rollback restores parent.

## LLM backend

- fake backend for deterministic unit tests;
- Ollama availability detection;
- missing model handled as SKIPPED_NOT_INSTALLED;
- timeout and one bounded retry;
- usage logging.

## End-to-end

Use a fake LLM that emits a tiny valid solver to test:

```text
bootstrap
→ sandbox
→ F1 evaluate
→ lineage save
→ critic decision
→ export
```

This test must not require a real Ollama model.

---

# 29. Implementation phases — follow this order

Do not try to implement the entire research vision at once.

## Phase 0 — delete old method and rename project

Acceptance:

```text
src/chargecegis is gone
old prompts are gone
old results are gone
old policy DSL is gone
old package/CLI is gone
new package imports
pytest starts from clean new tests
```

## Phase 1 — new fixed research infrastructure

Implement:

```text
problem contract
Schneider loader
canonical evaluator
candidate-solver interface
sandbox
result schemas
```

No LLM generation yet.

Acceptance: a manually written trivial candidate solver can be executed and scored.

## Phase 2 — model abstraction + five agent shells

Implement:

```text
Ollama backend
OpenAI-compatible backend
model registry
five prompts
agent schemas
fake backend
usage logging
```

Acceptance: every role can be invoked with fake/real backend and parsed deterministically.

## Phase 3 — Generation-0 solver synthesis

Implement:

```text
Architect bootstrap
specialist code creation
integration
compile repair
sandbox execution
F1 scoring
```

Acceptance: at least one configured LLM can autonomously produce an executable candidate solver from the EVRPTW specification without using an old prewritten optimizer.

## Phase 4 — code graph + targeted evolution

Implement:

```text
parent-child solver lineage
code replacement/patching
elite management
critic decisions
rollback
mechanism memory
```

Acceptance: one discovered solver can be improved through at least three logged generations.

## Phase 5 — multi-fidelity evaluation

Implement F0–F4 gates and deterministic split manifests.

Acceptance: weak candidates are rejected cheaply; elites can reach large-instance confirmation.

## Phase 6 — adaptive agent activation

Implement Architect-controlled role gating.

Acceptance: campaigns can freeze working components and invoke only relevant agents.

## Phase 7 — multi-model benchmark

Run homogeneous five-agent teams across 4–5 configured models.

Acceptance: one reproducible comparison table with equalized budgets.

## Phase 8 — team-size ablation

Run five-agent vs four-agent merged-Architect/Search configurations.

## Phase 9 — held-out final evaluation + export

Freeze solver before held-out run.

Export standalone solver.

---

# 30. Strict acceptance criteria for the migration

The migration is **not complete** merely because a few new files exist.

All of the following must be true.

## Old method removal

- [ ] `src/chargecegis/` does not exist.
- [ ] old five prompts do not exist.
- [ ] `policy_dsl.py` does not exist.
- [ ] old ranking methods do not exist in active source.
- [ ] old ChargeCEGIS results/manifests are removed from active results.
- [ ] old package name/CLI is removed.
- [ ] old ALNS is not silently renamed into the new proposed method.

## New method identity

- [ ] Generation-0 candidate solver code is produced by LLM agents.
- [ ] agents can create/edit multiple solver files.
- [ ] agents are not restricted to a scalar policy.
- [ ] no fixed classical solver controls the generated solver.
- [ ] generated code executes independently inside sandbox.
- [ ] final solver requires no LLM calls.

## Five agents

- [ ] Architect/Theorist implemented.
- [ ] Routing Engineer implemented.
- [ ] Charging Engineer implemented.
- [ ] Search/Integration Engineer implemented.
- [ ] Test/Evolution Critic implemented.
- [ ] roles have distinct prompts and schemas.
- [ ] roles have adaptive activation.

## Multi-model research

- [ ] arbitrary model profiles supported.
- [ ] at least 4, preferably 5, comparison profiles in config.
- [ ] homogeneous-team benchmark supported.
- [ ] model absence is handled explicitly.
- [ ] LLM token/time usage is logged.
- [ ] no silent model substitution.

## Team-size research

- [ ] five-agent configuration supported.
- [ ] four-agent merged Architect/Search configuration supported.
- [ ] equal-budget benchmark command implemented.

## Experimental integrity

- [ ] deterministic benchmark split manifest.
- [ ] held-out family inaccessible to discovery.
- [ ] F0–F4 evaluation funnel.
- [ ] matched parent-child evaluation.
- [ ] code lineage stored.
- [ ] mechanism memory stored.
- [ ] generated solver cannot read hidden answers.

## Code quality

- [ ] `pytest` passes.
- [ ] `ruff` passes.
- [ ] `mypy` has no new critical errors.
- [ ] README describes only the new project.
- [ ] generated artifacts are not committed accidentally unless explicitly desired.

---

# 31. Final grep / cleanup audit

After implementation, search the active repository for stale old-method concepts.

The migration instruction file itself may contain historical names; exclude it from this audit if it has been copied into the repository.

Examples:

```bash
grep -Rni --exclude='EVRPTW_AUTOLAB_CODING_AGENT_MIGRATION_SPEC.md' \
  -E 'chargecegis|REFERENCE_DSL|RANDOM_RANKING|FULL_FIVE_STAGE_LLM|ONE_SHOT_LLM|TYPED_GP|RANDOM_DSL|policy_dsl' \
  src tests configs prompts README.md pyproject.toml
```

Expected result:

```text
NO MATCHES
```

Also check that there is no active source file whose purpose is a fixed old ALNS host.

---

# 32. README wording for the new project

The new README should state the project clearly.

Suggested opening:

> **EVRPTW-AutoLab** is a multi-agent LLM system for autonomous synthesis of executable Electric Vehicle Routing Problem with Time Windows solvers. Five specialized agents act as an algorithm-development team: they design solver architectures, generate routing and charging algorithms, integrate search strategies, test candidate code on Schneider EVRPTW instances, diagnose failures, and iteratively evolve better solver implementations. The final discovered solver executes normally on CPU and requires no LLM calls at deployment time.

Also state explicitly:

> The project does not place an LLM scoring policy on top of a fixed EVRPTW optimizer. The optimizer itself is the generated research artifact.

---

# 33. Research questions the implementation must support

The codebase must make it possible to answer these later without a rewrite.

## RQ1 — Autonomous solver synthesis

Can a five-agent LLM team generate an executable EVRPTW solver from the problem specification and improve it through empirical experimentation?

## RQ2 — Model comparison

How do 4–5 local LLMs differ in:

- code validity;
- bootstrap success;
- debugging ability;
- effective algorithmic innovations;
- final solver quality;
- discovery cost?

## RQ3 — Agent specialization

Does the five-agent decomposition outperform a four-agent team or monolithic solver-design LLM under equalized discovery budgets?

## RQ4 — EV-specific specialization

Does a dedicated Charging & Constraint Engineer improve generated solver feasibility and performance relative to systems without that role?

## RQ5 — Evolution and memory

Does parent-child code evolution plus persistent mechanism memory outperform repeated from-scratch solver generation?

## RQ6 — Generalization

Does the discovered solver generalize to an unseen Schneider family without any LLM calls or additional synthesis?

---

# 34. What NOT to do during implementation

Do not:

- keep the old source package "for now" and make the new package depend on it;
- wrap the old ALNS and call it autonomous solver synthesis;
- make the agents generate only weights/formulas;
- reduce generated code to selecting predefined methods;
- ask LLMs to solve 100-customer instances token-by-token;
- expose held-out solutions/BKS to the discovery agents;
- use the final held-out family to choose the best model;
- compare five models with unequal evaluation budgets and call it fair;
- compare 5-agent vs 4-agent teams without controlling inference/evaluation budgets;
- run every candidate on all 92 instances;
- keep generating huge solver files from scratch after every small failure;
- silently repair generated solver code using a hidden handcrafted optimizer;
- silently substitute missing LLM models;
- add a sixth agent just for memory;
- preserve old ChargeCEGIS naming in active code/results.

---

# 35. Coding-agent completion report

When the migration is finished, provide a concise implementation report containing:

1. files/directories deleted;
2. new directory tree;
3. five agent roles implemented;
4. generated-solver interface;
5. sandbox/security approach;
6. model backends and configured comparison models;
7. four-agent and five-agent team configurations;
8. benchmark split/fidelity strategy;
9. tests executed and their results;
10. one end-to-end smoke example showing:

```text
LLM team
→ generated solver code
→ sandbox execution
→ EVRPTW result
→ evaluation
→ critic feedback
→ child solver
```

11. confirmation that the exported solver runs without any LLM backend;
12. remaining limitations/TODOs.

Do not claim the migration is complete until the end-to-end smoke pipeline is real.

---

# 36. Final instruction to the coding agent

**Perform a clean research-method reset.** Delete the previous ChargeCEGIS implementation and its active artifacts. Build EVRPTW-AutoLab as a fresh autonomous solver-synthesis framework.

The central invariant is:

```text
THE FIXED SYSTEM RUNS EXPERIMENTS.
THE LLM AGENTS CREATE THE OPTIMIZATION ALGORITHM.
```

The final research artifact is not a ranking formula and not an LLM-generated route. It is a **reusable executable EVRPTW solver whose algorithm was designed and evolved by the multi-agent LLM system**.

The framework must support both:

```text
5 specialized logical agents
```

and a controlled:

```text
4-agent ablation
```

and must support fair homogeneous-team comparisons across **4–5 different LLM models** without hard-coding the system to one model.

Do not preserve compatibility with the old method. Prioritize a clean, testable, reproducible implementation of this new research question.

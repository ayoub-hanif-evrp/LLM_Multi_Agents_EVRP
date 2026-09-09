# P1-B / synth01 — Controlled post-mortem (source-channel corruption)

**Status:** permanently recorded. Do not erase or re-label as an EVRPTW algorithmic failure.

**Verdict:**

> G2 failed because **non-code Critic/lesson prose entered `solver.py`**, producing a syntax error — a **software-channel / commit-integrity** failure — not because DeepSeek exhausted a valid charging algorithm under a hard AST gate.

---

## Pipeline stages

```text
raw LLM response (Charging.write_python)
        ↓
extract_python_source()   ← no AST check
        ↓
proposed solver.py string (contains "def solve")
        ↓
_write_solver()           ← unconditional commit on algo_fix path
        ↓
workspace/current/solver.py  CORRUPT
```

Raw responses were **not** persisted (`digest: null` in `llm_calls.jsonl`). Reconstruction uses archived attempt files + agent_log lessons.

---

## Answers

### 1. Which role produced the corrupt response?

**Charging** (coding role), twice:

| Archive | Status | Marker |
| --- | --- | --- |
| `G2_algo3_charging_solver.py` | SYNTAX line 23 | `energy_required_forupervisor: off topic; ...` |
| `G2_algo5_charging_solver.py` | SYNTAX line 23 | `energy_required_forupervisor: The mechanism-level lesson is...` |

Final `current/solver.py` hash matches **`G2_algo5_charging`**.

### 2. Did the raw model response itself contain the lesson inside the Python?

**Almost certainly yes (model-output corruption).** We lack the raw dump, but the committed file is the extract of Charging’s `write_python` output. The spliced text matches the Critic **lesson** that was only present in the Charging **prompt** (`Critic mechanism: {lesson}`), glued mid-identifier:

```text
remaining_energy -= energy_required_forupervisor: The mechanism-level lesson is that ...
```

That is not a clean Autolab string join of two files; it is incomplete token `energy_required_for` + foreign prose.

### 3. Or did AutoLab concatenate Critic content into coding output?

**No file-level concatenation.** Critic returns JSON via `Agent.run()` only. Lesson text is passed **into the Charging instruction string**. Autolab did not append Critic JSON onto `solver.py` after extraction. The failure mode is: **prompt leakage echoed by the coder into the Python payload**, then accepted.

### 4. Did the parser accept prose after a code fence?

`extract_python_source` accepts:

- fenced ```python``` bodies (longest wins), or
- entire raw text if no fence

It does **not** require `ast.parse`. Any string containing `def solve` can be committed on the algo path — including prose spliced into identifiers.

### 5. Why was syntactically invalid code allowed to replace the last valid G1 solver?

In `p1_minimal._run_gate`, algorithmic fixes do:

```text
if "def solve" in source:
    _write_solver(solver_dir, source)   # no AST gate
```

Only `_coding_repair` partially checks `ast.parse`, and only after a crash is already detected. **Algo commits bypass the gate.**

### 6. Why wasn’t `ast.parse()` / `compile()` a hard pre-commit gate?

It was never required on the specialist write path. Integrity was treated as optional post-hoc repair instead of transactional commit.

### 7. Was the Critic ever allowed to modify a source file?

**No.** Critic has **no** `write_python` / `_write_solver` path. Architect likewise plans only. Indirect effect: Critic lesson text in the Charging prompt was **echoed into** corrupt Python by Charging.

### 8. Last syntactically valid solver before final corruption — G2 behavior?

Immediately before `G2_algo5_charging`:

| Checkpoint | Syntax | G1 | G2 |
| --- | --- | --- | --- |
| `G0_repair0_search` (G1 incumbent) | VALID | **OK** | **BATTERY** |
| `G2_algo0_charging` | VALID | OK | BATTERY |
| `G2_algo2_routing_after_noop` | VALID | DEPOT | DEPOT |
| `G2_repair0_search` (fixed algo3 syntax) | VALID | VISIT | VISIT |
| `G2_algo4_routing` (last valid before algo5) | VALID | VISIT | VISIT |

**Important:** DeepSeek **had** reached a meaningful EVRPTW state earlier: **G1 feasible + G2 BATTERY** (charging required). That is an algorithmic signal. The lab then allowed later invalid commits (and earlier valid but incomplete VISIT solvers) to destroy that checkpoint.

`G2_algo4_routing` builds `new_route` but **never appends** to `routes` → VISIT — still syntactically valid.

---

## Root-cause classification

| Hypothesis | Supported? |
| --- | --- |
| DeepSeek cannot reason about G2 charging | **Not established** by synth01 (earlier BATTERY on valid code) |
| Code-channel corruption / missing commit gate | **Yes** |
| Critic wrote the file | No |
| Parser/AST pre-commit missing | **Yes** |

$$
\boxed{algorithm failure \neq code-channel corruption}
$$

synth01 records the latter.

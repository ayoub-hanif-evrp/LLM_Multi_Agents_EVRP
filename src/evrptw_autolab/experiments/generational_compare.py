"""Multi-generation comparison with equal panel-evaluation budgets.

Generation 0 of each search arm is the one-shot control: it does not see
fitness feedback. Later generations mutate a parent and do see it. Critic
text guides the next five-agent proposal and does not add a solver run.
"""
from __future__ import annotations

import json
import random
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evrptw_autolab.components.expressions import ARGUMENT_NAMES, wrap_expression
from evrptw_autolab.components.interfaces import DEFAULT_SOURCES, ComponentKind
from evrptw_autolab.components.loader import load_bundle
from evrptw_autolab.experiments.bundle_selection import conservative_decision
from evrptw_autolab.experiments.fair_budget import DECLARED_SELECTION_RULE, SEARCH_CANDIDATES
from evrptw_autolab.experiments.matched_pilot import (
    KINDS,
    MatchedPilotConfig,
    _backend,
    _critic,
    _evaluate,
    _pairs,
    _panel,
    _propose_five,
    _propose_single,
)
from evrptw_autolab.llm.usage import UsageCollector
from evrptw_autolab.problem.v2.features import FEATURE_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[3]
_PROBES: dict[ComponentKind, tuple[tuple[float, ...], ...]] = {
    "insertion_score": ((1.0, 10.0, 0.0, 1.0, 5.0), (5.0, 1.0e6, 0.0, 1.0, 0.0)),
    "station_score": ((1.0, 0.2, 2.0), (3.0, 0.0, 1.0)),
    "removal_priority": ((10.0, 0.5, 0.2), (1.0e6, 0.1, 0.9)),
}


@dataclass
class GenerationalConfig:
    seed: int = 7
    fake: bool = False
    micro: bool = False
    candidates: int = SEARCH_CANDIDATES
    use_critic: bool = True
    out_dir: Path | None = None


def _grammar(kind: ComponentKind, rng: random.Random) -> str:
    names = list(ARGUMENT_NAMES[kind])
    coeffs = ("0.01", "0.1", "1.0", "5.0", "10.0")
    left = rng.choice(names)
    right = rng.choice(names)
    coeff = rng.choice(coeffs)
    other = rng.choice(coeffs)
    draw = rng.randrange(4)
    if draw == 0:
        return f"{left} + {coeff} * {right}"
    if draw == 1:
        return f"max(0.0, {left} - {coeff} * {right})"
    if draw == 2:
        return f"{coeff} * {left} + {other} * {right}"
    return f"min({left}, {coeff} * {right})"


def _changed(sources: dict[ComponentKind, str]) -> bool:
    defaults = {kind: DEFAULT_SOURCES[kind] for kind in KINDS}
    baseline, _ = load_bundle(defaults, {kind: "default" for kind in KINDS})
    trial, errors = load_bundle(sources, {kind: "trial" for kind in sources})
    if errors:
        return False
    for kind, points in _PROBES.items():
        left = getattr(baseline, kind, None)
        right = getattr(trial, kind, None)
        if left is None or right is None:
            continue
        for point in points:
            try:
                if abs(float(left(*point)) - float(right(*point))) > 1e-9:
                    return True
            except (TypeError, ValueError):
                return True
    return False


def _feedback(rows: list[dict[str, Any]], decision: dict[str, Any]) -> str:
    bits = [
        f"{row['instance_id']}: feasible={row['feasible']} key={row['objective_key']} fault={row['first_fault']}"
        for row in rows
    ]
    return f"selection={decision.get('reason')} wins={decision.get('wins')} losses={decision.get('losses')}; " + "; ".join(bits)


def _record(
    arm: str,
    generation: int,
    parent_id: str,
    candidate_id: str,
    sources: dict[ComponentKind, str],
    rows: list[dict[str, Any]],
    baseline: list[dict[str, Any]],
    *,
    mutation: str,
    origin: str,
) -> dict[str, Any]:
    changed = _changed(sources)
    decision = conservative_decision(_pairs(baseline, rows))
    accepted = bool(decision["accepted"]) and changed
    if decision["accepted"] and not changed:
        decision = dict(decision)
        decision["accepted"] = False
        decision["reason"] = "no_decision_change"
    return {
        "arm": arm,
        "generation": generation,
        "oneshot": generation == 0,
        "parent_id": parent_id,
        "candidate_id": candidate_id,
        "mutation": mutation,
        "origin": origin,
        "behavior_changed": changed,
        "decision": decision,
        "accepted": accepted,
        "sources": {kind: sources[kind] for kind in KINDS},
        "feature_schema": (
            str(rows[0].get("feature_schema") or FEATURE_SCHEMA_VERSION)
            if rows
            else FEATURE_SCHEMA_VERSION
        ),
        "source_hashes": {kind: _digest(text) for kind, text in sources.items()},
        "rows": rows,
    }


def _progress(item: dict[str, Any]) -> None:
    decision = item["decision"]
    print(
        {
            "arm": item["arm"],
            "generation": item["generation"],
            "accepted": item["accepted"],
            "reason": decision.get("reason"),
            "wins": decision.get("wins"),
            "losses": decision.get("losses"),
            "changed": item["behavior_changed"],
        },
        flush=True,
    )


def _digest(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _run_random(panel: list[Any], baseline: list[dict[str, Any]], seed: int, candidates: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    parent_sources = {kind: DEFAULT_SOURCES[kind] for kind in KINDS}
    parent_id = "classical"
    history = []
    for generation in range(candidates):
        sources = dict(parent_sources)
        kind = KINDS[generation % len(KINDS)]
        expression = _grammar(kind, rng)
        sources[kind] = wrap_expression(kind, expression)
        rows = _evaluate(
            "random_evolution",
            f"random_g{generation}",
            sources,
            FEATURE_SCHEMA_VERSION,
            panel,
            seed,
            extra={"generation": generation, "origin": "grammar", "llm_generated_components": 0},
        )
        item = _record(
            "random_evolution",
            generation,
            parent_id,
            f"random_g{generation}",
            sources,
            rows,
            baseline,
            mutation=f"{kind}: {expression}",
            origin="grammar",
        )
        history.append(item)
        _progress(item)
        if item["accepted"]:
            parent_sources = sources
            parent_id = item["candidate_id"]
    return history


def _run_single(
    panel: list[Any],
    baseline: list[dict[str, Any]],
    seed: int,
    candidates: int,
    backend: Any,
    model: str,
) -> tuple[list[dict[str, Any]], UsageCollector]:
    collector = UsageCollector(max_calls=candidates * 3, max_tokens=20000)
    parent_id = "classical"
    feedback = ""
    families = sorted({item.family for item in panel})
    history = []
    for generation in range(candidates):
        sources, attribution, schema = _propose_single(
            collector,
            backend,
            model,
            families=families,
            index=generation,
            feedback=feedback,
        )
        genuine = sum(1 for row in attribution if row.get("llm_generated"))
        rows = _evaluate(
            "single_agent",
            f"single_g{generation}",
            sources,
            schema,
            panel,
            seed,
            extra={"generation": generation, "origin": "llm", "llm_generated_components": genuine},
        )
        item = _record(
            "single_agent",
            generation,
            parent_id,
            f"single_g{generation}",
            sources,
            rows,
            baseline,
            mutation="unified expression bundle",
            origin="llm",
        )
        item["attribution"] = [{key: row[key] for key in row if key != "source"} for row in attribution]
        history.append(item)
        _progress(item)
        feedback = _feedback(rows, item["decision"])
        if item["accepted"]:
            parent_id = item["candidate_id"]
    return history, collector


def _run_five(
    panel: list[Any],
    baseline: list[dict[str, Any]],
    seed: int,
    candidates: int,
    backend: Any,
    model: str,
    *,
    use_critic: bool,
) -> tuple[list[dict[str, Any]], UsageCollector]:
    collector = UsageCollector(max_calls=candidates * 8, max_tokens=40000)
    parent_id = "classical"
    critic_text = ""
    families = sorted({item.family for item in panel})
    history = []
    for generation in range(candidates):
        sources, attribution, schema, plan = _propose_five(
            collector,
            backend,
            model,
            families=families,
            index=generation,
            critic_text=critic_text,
        )
        genuine = sum(1 for row in attribution if row.get("llm_generated"))
        rows = _evaluate(
            "five_agent",
            f"five_g{generation}",
            sources,
            schema,
            panel,
            seed,
            extra={"generation": generation, "origin": "llm", "llm_generated_components": genuine},
        )
        item = _record(
            "five_agent",
            generation,
            parent_id,
            f"five_g{generation}",
            sources,
            rows,
            baseline,
            mutation=str(plan.get("hypothesis") or ""),
            origin="llm",
        )
        item["architect"] = plan
        item["attribution"] = [{key: row[key] for key in row if key != "source"} for row in attribution]
        if use_critic:
            critic_text = _critic(collector, backend, model, rows)
            item["critic"] = critic_text
        else:
            critic_text = ""
            item["critic"] = None
        history.append(item)
        _progress(item)
        if item["accepted"]:
            parent_id = item["candidate_id"]
    return history, collector


def _ollama_digest(model: str) -> str | None:
    if model == "fake":
        return None
    try:
        text = subprocess.check_output(
            ["ollama", "show", model, "--modelfile"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    for line in text.splitlines():
        if "sha256-" not in line:
            continue
        token = line.split("sha256-", 1)[1].split()[0].strip()
        return f"sha256-{token}"
    return None


def _selected(history: list[dict[str, Any]]) -> str | None:
    for item in history:
        if item["accepted"]:
            return str(item["candidate_id"])
    return None


def run_generational(cfg: GenerationalConfig | None = None) -> dict[str, Any]:
    cfg = cfg or GenerationalConfig()
    panel_cfg = MatchedPilotConfig(
        seed=cfg.seed,
        fake=cfg.fake,
        micro=cfg.micro,
        candidates=cfg.candidates,
    )
    panel = _panel(panel_cfg)
    backend, model = _backend(panel_cfg)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    label = "fake" if cfg.fake else "qwen"
    critic = "" if cfg.use_critic else "_no_critic"
    out = cfg.out_dir or (ROOT / "results" / "v2" / "campaigns" / f"generational_{label}{critic}_{stamp}")
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    classical_sources = {kind: DEFAULT_SOURCES[kind] for kind in KINDS}
    baseline = _evaluate("classical", "default", classical_sources, FEATURE_SCHEMA_VERSION, panel, cfg.seed)
    print({"arm": "classical", "rows": len(baseline)}, flush=True)
    (out / "partial.json").write_text(
        json.dumps({"status": "classical_done", "classical": baseline}, indent=2) + "\n",
        encoding="utf-8",
    )
    random_history = _run_random(panel, baseline, cfg.seed, cfg.candidates)
    (out / "partial.json").write_text(
        json.dumps(
            {"status": "random_done", "classical": baseline, "random_evolution": random_history},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    single_history, single_usage = _run_single(panel, baseline, cfg.seed, cfg.candidates, backend, model)
    five_history, five_usage = _run_five(
        panel,
        baseline,
        cfg.seed,
        cfg.candidates,
        backend,
        model,
        use_critic=cfg.use_critic,
    )
    solves = {
        "classical": len(baseline),
        "random_evolution": cfg.candidates * len(panel),
        "single_agent": cfg.candidates * len(panel),
        "five_agent": cfg.candidates * len(panel),
    }
    payload = {
        "protocol": "generational_equal_panel_evaluations",
        "selection_rule": DECLARED_SELECTION_RULE,
        "model": model,
        "model_digest": _ollama_digest(model),
        "fake": cfg.fake,
        "seed": cfg.seed,
        "candidates": cfg.candidates,
        "use_critic": cfg.use_critic,
        "oneshot_definition": "generation 0 receives no fitness feedback",
        "solver_solves": solves,
        "llm_calls": {
            "single_agent": single_usage.logical_calls,
            "five_agent": five_usage.logical_calls,
            "random_evolution": 0,
            "classical": 0,
        },
        "llm_tokens": {
            "single_agent": single_usage.total_tokens,
            "five_agent": five_usage.total_tokens,
            "random_evolution": 0,
            "classical": 0,
        },
        "selected": {
            "random_evolution": _selected(random_history),
            "single_agent": _selected(single_history),
            "five_agent": _selected(five_history),
        },
        "classical": baseline,
        "random_evolution": random_history,
        "single_agent": single_history,
        "five_agent": five_history,
        "wall_s": round(time.monotonic() - started, 3),
        "artifact": str(out / "generational.json"),
        "claim": (
            "Generation 0 is the one-shot control. Later generations are accepted "
            "only by the conservative rule and only if a probe score changed. "
            "FakeBackend rows are not model evidence."
        ),
    }
    (out / "generational.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--fake", action="store_true")
    parser.add_argument("--micro", action="store_true")
    parser.add_argument("--no-critic", action="store_true")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--candidates", type=int, default=SEARCH_CANDIDATES)
    args = parser.parse_args()
    result = run_generational(
        GenerationalConfig(
            seed=args.seed,
            fake=args.fake,
            micro=args.micro,
            candidates=args.candidates,
            use_critic=not args.no_critic,
        )
    )
    print(
        {
            "model": result["model"],
            "solves": result["solver_solves"],
            "tokens": result["llm_tokens"],
            "selected": result["selected"],
            "wall_s": result["wall_s"],
        },
        flush=True,
    )


if __name__ == "__main__":
    main()

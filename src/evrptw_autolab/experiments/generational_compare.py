"""Multi-generation comparison with equal panel-evaluation budgets.

Every search arm replaces one scheduled component of its accepted parent.
Generation 0 does not see fitness feedback. Later generations do. The critic
sees the classical baseline and does not add a solver evaluation. Single-agent
and five-agent share one token cap.
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

from evrptw_autolab.components.expressions import wrap_expression
from evrptw_autolab.components.interfaces import DEFAULT_SOURCES, ComponentKind
from evrptw_autolab.components.loader import load_bundle
from evrptw_autolab.experiments.bundle_selection import (
    conservative_decision,
    random_component_expression,
)
from evrptw_autolab.experiments.fair_budget import DECLARED_SELECTION_RULE, SEARCH_CANDIDATES
from evrptw_autolab.experiments.matched_pilot import (
    KINDS,
    MatchedPilotConfig,
    _backend,
    _critic,
    _evaluate,
    _pairs,
    _panel,
    _propose_component,
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
    return random_component_expression(kind, rng)


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


def _feedback(rows: list[dict[str, Any]], decision: dict[str, Any], baseline: list[dict[str, Any]]) -> str:
    base = {str(row["instance_id"]): row for row in baseline}
    bits = []
    for row in rows:
        other = base[str(row["instance_id"])]
        bits.append(
            f"{row['instance_id']}: classical_key={other['objective_key']} "
            f"candidate_key={row['objective_key']} feasible={row['feasible']} fault={row['first_fault']}"
        )
    return (
        f"selection={decision.get('reason')} wins={decision.get('wins')} losses={decision.get('losses')}; "
        + "; ".join(bits)
    )


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


_TOKEN_CAP = 20000


def _apply_component(
    parent_sources: dict[ComponentKind, str],
    parent_schema: str,
    kind: ComponentKind,
    code: str,
    schema: str,
) -> tuple[dict[ComponentKind, str], str]:
    sources = dict(parent_sources)
    sources[kind] = code
    if kind == "station_score":
        return sources, schema
    return sources, parent_schema


def _run_single(
    panel: list[Any],
    baseline: list[dict[str, Any]],
    seed: int,
    candidates: int,
    backend: Any,
    model: str,
) -> tuple[list[dict[str, Any]], UsageCollector]:
    collector = UsageCollector(max_calls=candidates * 3, max_tokens=_TOKEN_CAP)
    parent_sources = {kind: DEFAULT_SOURCES[kind] for kind in KINDS}
    parent_schema = FEATURE_SCHEMA_VERSION
    parent_id = "classical"
    feedback = ""
    history = []
    for generation in range(candidates):
        kind = KINDS[generation % len(KINDS)]
        code, row, schema = _propose_component(
            collector,
            backend,
            model,
            kind,
            context=f"Generation {generation}. {feedback or 'No fitness feedback yet.'}",
        )
        sources, use_schema = _apply_component(parent_sources, parent_schema, kind, code, schema)
        genuine = 1 if row.get("llm_generated") else 0
        rows = _evaluate(
            "single_agent",
            f"single_g{generation}",
            sources,
            use_schema,
            panel,
            seed,
            extra={"generation": generation, "origin": "llm", "llm_generated_components": genuine, "component": kind},
        )
        item = _record(
            "single_agent",
            generation,
            parent_id,
            f"single_g{generation}",
            sources,
            rows,
            baseline,
            mutation=f"{kind}: parent mutation",
            origin="llm",
        )
        item["attribution"] = [{key: value for key, value in row.items() if key != "source"}]
        history.append(item)
        _progress(item)
        feedback = _feedback(rows, item["decision"], baseline)
        if item["accepted"]:
            parent_sources = sources
            parent_schema = use_schema
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
    collector = UsageCollector(max_calls=candidates * 4, max_tokens=_TOKEN_CAP)
    parent_sources = {kind: DEFAULT_SOURCES[kind] for kind in KINDS}
    parent_schema = FEATURE_SCHEMA_VERSION
    parent_id = "classical"
    critic_text = ""
    history = []
    for generation in range(candidates):
        kind = KINDS[generation % len(KINDS)]
        context = f"Generation {generation}. Prior critic: {critic_text or 'none'}."
        code, row, schema = _propose_component(
            collector,
            backend,
            model,
            kind,
            context=context,
        )
        sources, use_schema = _apply_component(parent_sources, parent_schema, kind, code, schema)
        genuine = 1 if row.get("llm_generated") else 0
        rows = _evaluate(
            "five_agent",
            f"five_g{generation}",
            sources,
            use_schema,
            panel,
            seed,
            extra={"generation": generation, "origin": "llm", "llm_generated_components": genuine, "component": kind},
        )
        item = _record(
            "five_agent",
            generation,
            parent_id,
            f"five_g{generation}",
            sources,
            rows,
            baseline,
            mutation=f"{kind}: parent mutation",
            origin="llm",
        )
        item["attribution"] = [{key: value for key, value in row.items() if key != "source"}]
        if use_critic:
            critic_text = _critic(collector, backend, model, rows, baseline)
            item["critic"] = critic_text
        else:
            critic_text = ""
            item["critic"] = None
        history.append(item)
        _progress(item)
        if item["accepted"]:
            parent_sources = sources
            parent_schema = use_schema
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
    accepted = [item for item in history if item["accepted"]]
    if not accepted:
        return None
    best = max(accepted, key=lambda item: (int(item["decision"].get("wins") or 0), -int(item["generation"])))
    return str(best["candidate_id"])


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
            "Each generation mutates one scheduled component of the accepted parent. "
            "Generation 0 receives no fitness feedback. Acceptance uses the conservative "
            "rule and requires a probe-score change. The deployed candidate is the "
            "accepted one with the most wins. Single-agent and five-agent share one "
            "token cap. The critic sees the classical keys and adds no solver evaluation. "
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

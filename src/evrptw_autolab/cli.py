"""CIPHER-EVRP command line. Classical solving and contract checks only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.discovery.schemas import OperatorSpec
from evrptw_autolab.problem.datasets.bezzi import discover_bezzi, load_bezzi
from evrptw_autolab.problem.datasets.goeke import discover_goeke, load_goeke
from evrptw_autolab.problem.datasets.hiermann import discover_hiermann, load_hiermann
from evrptw_autolab.problem.datasets.montoya import discover_montoya, load_montoya
from evrptw_autolab.problem.datasets.registry import audit_all
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
from evrptw_autolab.problem.schneider import discover_instances
from evrptw_autolab.transfer.hard_compatibility import compatibility_failures

app = typer.Typer(no_args_is_help=True, add_completion=False)
datasets_app = typer.Typer(no_args_is_help=True, help="Audit the five benchmark families.")
solver_app = typer.Typer(no_args_is_help=True, help="Run the classical optimizer.")
policies_app = typer.Typer(no_args_is_help=True, help="Check an operator specification.")
app.add_typer(datasets_app, name="datasets")
app.add_typer(solver_app, name="solver")
app.add_typer(policies_app, name="policies")

ROOT = Path(__file__).resolve().parents[2]

_LOADERS = {
    "schneider": (discover_instances, load_schneider_v2),
    "montoya": (discover_montoya, load_montoya),
    "bezzi": (discover_bezzi, load_bezzi),
    "goeke": (discover_goeke, load_goeke),
    "hiermann": (discover_hiermann, load_hiermann),
}


def main() -> None:
    app()


def _find_instance(family: str, instance: str) -> Path:
    discover, _loader = _LOADERS[family]
    matches = [path for path in discover() if path.stem == instance or path.name == instance]
    if len(matches) != 1:
        raise typer.BadParameter(f"{family} instance {instance!r} matched {len(matches)} files")
    return matches[0]


@datasets_app.command("validate")
def datasets_validate() -> None:
    """Load every discovered benchmark file and report parse failures."""
    audits = audit_all()
    summary = {
        audit.family_id: {
            "instances": audit.instance_file_count,
            "loaded": audit.loaded_count,
            "status": audit.parse_status,
        }
        for audit in audits
    }
    typer.echo(json.dumps(summary, indent=2))
    if any(audit.parse_status == "failed" for audit in audits):
        raise typer.Exit(code=1)


@solver_app.command("run")
def solver_run(
    family: str = typer.Option(..., "--family"),
    instance: str = typer.Option(..., "--instance"),
    seed: int = typer.Option(1, "--seed"),
    time_limit_s: float = typer.Option(5.0, "--time-limit"),
    iterations: int = typer.Option(20, "--iterations"),
    partition: str = typer.Option(..., "--partition", help="development|discovery|confirmation|heldout"),
) -> None:
    """Solve one instance with the classical engine and the trusted evaluator."""
    if family not in _LOADERS:
        raise typer.BadParameter(f"family must be one of {sorted(_LOADERS)}")
    if partition not in {"development", "discovery", "confirmation", "heldout"}:
        raise typer.BadParameter("partition must be development, discovery, confirmation, or heldout")
    path = _find_instance(family, instance)
    _discover, loader = _LOADERS[family]
    spec = loader(path)
    solution = solve_classical(
        spec,
        seed=seed,
        time_limit_s=time_limit_s,
        alns_iterations=iterations,
        experiment_partition=partition,
    )
    report = evaluate(spec, solution)
    typer.echo(
        json.dumps(
            {
                "family": family,
                "instance": spec.instance_id,
                "feasible": bool(report.feasible),
                "objective_key": [float(value) for value in report.objective_key],
                "vehicles": report.vehicles,
                "llm_calls": 0,
                "attribution": "classical_baseline",
            },
            indent=2,
        )
    )
    if not report.feasible:
        raise typer.Exit(code=1)


@policies_app.command("validate")
def policies_validate(
    policy: Path = typer.Option(..., "--policy", exists=True, dir_okay=False),
    family: str = typer.Option(..., "--family"),
) -> None:
    """Reject an operator whose hard capability requirements the family does not meet."""
    if family not in _LOADERS:
        raise typer.BadParameter(f"family must be one of {sorted(_LOADERS)}")
    spec = OperatorSpec.model_validate_json(policy.read_text(encoding="utf-8"))
    path = _find_instance(family, _default_probe(family))
    _discover, loader = _LOADERS[family]
    problem = loader(path)
    failures = compatibility_failures(spec, problem.capabilities)
    typer.echo(json.dumps({"operator_id": spec.operator_id, "failures": failures}, indent=2))
    if failures:
        raise typer.Exit(code=1)


counterexamples_app = typer.Typer(no_args_is_help=True, help="Mine a development counterexample.")
discovery_app = typer.Typer(no_args_is_help=True, help="Run one scripted discovery cycle.")
transfer_app = typer.Typer(no_args_is_help=True, help="Fit an applicability rule on development examples.")
research_app = typer.Typer(no_args_is_help=True, help="Report the scripted one-family comparison.")
app.add_typer(counterexamples_app, name="counterexamples")
app.add_typer(discovery_app, name="discovery")
app.add_typer(transfer_app, name="transfer")
app.add_typer(research_app, name="research")


def _load_yaml(name: str) -> dict[str, Any]:
    import yaml

    path = ROOT / "configs" / name
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


@counterexamples_app.command("generate")
def counterexamples_generate() -> None:
    """Record the longer-detour regression on the declared development repair."""
    import random

    from evrptw_autolab.backbone.alns import repair_greedy
    from evrptw_autolab.discovery.schemas import OperatorSpec
    from evrptw_autolab.research.panel import development_case
    from evrptw_autolab.transfer.counterexamples import refuse_non_development

    config = _load_yaml("counterexamples.yaml")
    partition = str(config.get("partition", "development"))
    refuse_non_development(partition)

    spec, solution, removed = development_case()
    operator = OperatorSpec(
        operator_id="long_detour",
        version="1",
        source_agent="cli",
        description="Prefer the longer detour.",
        operator_family="repair",
        implementation_reference="repair_greedy",
        required_capabilities=["time_windows"],
        applicability_rule="1",
        candidate_scoring_policy="-1 * delta_distance",
        mine_counterexamples=True,
        fallback_operator="classical_default",
    )
    repaired = repair_greedy(spec, solution, removed, random.Random(1), operator, partition=partition)
    typer.echo(json.dumps({"llm_calls": 0, "counterexamples": repaired.metadata.get("counterexamples", [])}, indent=2))


@discovery_app.command("run")
def discovery_run(
    max_calls: int | None = typer.Option(None, "--max-calls"),
    backend: str | None = typer.Option(None, "--backend"),
    model_id: str | None = typer.Option(None, "--model-id"),
    live: bool = typer.Option(False, "--live", help="Allow a live Ollama backend."),
) -> None:
    """Run discovery. Default backend is fake. Live Ollama requires --live."""
    from evrptw_autolab.discovery.controller import run_live_cycle, run_scripted_cycle

    config = _load_yaml("discovery.yaml")
    chosen = str(backend or config.get("backend") or "fake")
    configured = config.get("max_llm_calls", 4)
    limit = max_calls if max_calls is not None else int(configured)
    if limit > 20:
        raise typer.BadParameter("the discovery cap is 20 calls")
    if chosen == "fake":
        result = run_scripted_cycle(max_calls=limit)
    elif chosen == "ollama":
        if not live and str(config.get("allow_live", "false")).lower() not in {"1", "true", "yes"}:
            raise typer.BadParameter("live Ollama discovery requires --live or allow_live: true")
        result = run_live_cycle(
            model_id=str(model_id or config.get("model_id") or "qwen25_coder_14b"),
            max_calls=limit,
            wall_s=float(config.get("wall_s", 600)),
            max_tokens=int(config.get("max_tokens", 8000)),
        )
    else:
        raise typer.BadParameter("backend must be fake or ollama")
    typer.echo(
        json.dumps(
            {
                "backend": result.get("backend", chosen),
                "model_id": result.get("model_id"),
                "llm_calls": result["llm_calls"],
                "prompt_tokens": result.get("prompt_tokens", 0),
                "completion_tokens": result.get("completion_tokens", 0),
                "roles": result.get("roles"),
                "applicability_rule": result["operator"]["applicability_rule"],
                "action": (result.get("decision") or {}).get("action"),
                "counterexamples": len(result.get("counterexamples") or []),
            },
            indent=2,
        )
    )


@transfer_app.command("evaluate")
def transfer_evaluate() -> None:
    """Fit one development stump. Confirmation and held-out rows are not accepted here."""
    from evrptw_autolab.transfer.applicability import ApplicabilityExample, fit_stump
    from evrptw_autolab.transfer.counterexamples import refuse_non_development

    config = _load_yaml("transfer.yaml")
    refuse_non_development(str(config.get("train_partition", "development")))
    stump = fit_stump(
        [
            ApplicabilityExample({"route_utilization": 0.2}, False, "development"),
            ApplicabilityExample({"route_utilization": 0.95}, True, "discovery"),
        ]
    )
    typer.echo(json.dumps({"rule": stump.rule(), "trained": stump.trained, "llm_calls": 0}, indent=2))


@research_app.command("report")
def research_report() -> None:
    """Write the scripted B0–B6 comparison. It is not a live-model result."""
    from evrptw_autolab.research.compare import scripted_report

    report = scripted_report()
    destination = ROOT / "results" / "cipher" / "scripted_comparison.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    typer.echo(json.dumps(report, indent=2))


@research_app.command("freeze-classical")
def research_freeze_classical() -> None:
    """Freeze the Schneider+Hiermann classical development panel. Zero LLM calls."""
    from evrptw_autolab.research.classical_freeze import freeze_panel

    payload = freeze_panel()
    typer.echo(json.dumps({"rows": len(payload["rows"]), "llm_calls": 0, "path": "results/cipher/classical/development_panel.json"}, indent=2))


@research_app.command("live-signal")
def research_live_signal(
    backend: str = typer.Option("fake", "--backend"),
    model_id: str = typer.Option("qwen25_coder_14b", "--model-id"),
    max_calls: int = typer.Option(4, "--max-calls"),
    live: bool = typer.Option(False, "--live"),
) -> None:
    """One capped discovery then paired Schneider/Hiermann solves."""
    from evrptw_autolab.research.live_signal import run_signal

    if backend == "ollama" and not live:
        raise typer.BadParameter("live Ollama signal requires --live")
    if max_calls > 20:
        raise typer.BadParameter("the discovery cap is 20 calls")
    payload = run_signal(backend=backend, model_id=model_id, max_calls=max_calls)
    typer.echo(
        json.dumps(
            {
                "gate": payload["gate"],
                "backend": payload["backend"],
                "llm_calls": payload["llm_calls"],
                "paired": len(payload["paired"]),
                "path": f"results/cipher/live_signal/{backend}_signal.json",
            },
            indent=2,
        )
    )


def _default_probe(family: str) -> str:
    discover, _loader = _LOADERS[family]
    paths = discover()
    if not paths:
        raise typer.BadParameter(f"{family} has no instances")
    return paths[0].stem

"""CIPHER-EVRP command line. Classical solving and contract checks only."""

from __future__ import annotations

import json
from pathlib import Path

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
) -> None:
    """Solve one instance with the classical engine and the trusted evaluator."""
    if family not in _LOADERS:
        raise typer.BadParameter(f"family must be one of {sorted(_LOADERS)}")
    path = _find_instance(family, instance)
    _discover, loader = _LOADERS[family]
    spec = loader(path)
    solution = solve_classical(
        spec,
        seed=seed,
        time_limit_s=time_limit_s,
        alns_iterations=iterations,
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


def _default_probe(family: str) -> str:
    discover, _loader = _LOADERS[family]
    paths = discover()
    if not paths:
        raise typer.BadParameter(f"{family} has no instances")
    return paths[0].stem

"""VoltForge CLI. Team size is fixed at five agents; models vary."""
from __future__ import annotations

import json
from pathlib import Path

import typer
import yaml

from evrptw_autolab.evaluation.fidelity import load_all, split_instances, write_split_manifest
from evrptw_autolab.evaluation.runner import evaluate_fidelity
from evrptw_autolab.experiments.heldout import run_heldout
from evrptw_autolab.experiments.model_benchmark import benchmark_models
from evrptw_autolab.experiments.synthesis_campaign import run_campaign
from evrptw_autolab.llm.ollama import OllamaBackend
from evrptw_autolab.llm.registry import (
    SKIPPED_NOT_INSTALLED,
    availability,
    list_profiles,
    make_backend,
    resolve_profile,
)
from evrptw_autolab.orchestration.state import CampaignState
from evrptw_autolab.problem.hashes import write_instance_hashes
from evrptw_autolab.problem.private import smoke_instance
from evrptw_autolab.problem.schneider import SCHNEIDER_ROOT, discover_instances
from evrptw_autolab.sandbox.limits import RunLimits
from evrptw_autolab.synthesis.bootstrap import bootstrap_solver
from evrptw_autolab.synthesis.export import export_solver

app = typer.Typer(no_args_is_help=True, add_completion=False)
models_app = typer.Typer(no_args_is_help=True, help="Inspect configured LLM model profiles.")
app.add_typer(models_app, name="models")
ROOT = Path(__file__).resolve().parents[2]


def _require_five_agent(team: str) -> None:
    if team != "five_agent":
        raise typer.BadParameter("only five_agent is supported; models vary, not agent count")


def json_dumps(payload: object) -> str:
    return json.dumps(payload, indent=2, default=str)


def _solver_dir(solver_id: str) -> Path:
    candidates = [
        ROOT / "workspace" / "candidates" / solver_id,
        ROOT / "workspace" / "discovery" / solver_id,
    ]
    discovery_root = ROOT / "workspace" / "discovery"
    if discovery_root.exists():
        candidates.extend(sorted(discovery_root.glob(f"*/candidates/{solver_id}")))
    path = next((item for item in candidates if item.exists()), None)
    if path is None:
        raise typer.BadParameter(f"solver not found: {solver_id}")
    return path


@app.command("validate-data")
def validate_data() -> None:
    paths = discover_instances(ROOT / SCHNEIDER_ROOT)
    instances = load_all(ROOT / SCHNEIDER_ROOT)
    split = split_instances(instances)
    manifest = write_split_manifest(ROOT / "results" / "manifests" / "split.json", split)
    hashes = write_instance_hashes(ROOT / "results" / "manifests" / "instance_hashes.json")
    typer.echo(
        f"OK {len(paths)} Schneider instances; discovery={len(split['discovery'])} "
        f"confirmation={len(split['confirmation'])} heldout={len(split['heldout'])} "
        f"manifest={manifest} hashes={hashes}"
    )


@models_app.command("list")
def models_list() -> None:
    ollama = OllamaBackend()
    for profile in list_profiles():
        status = availability(profile, ollama)
        flag = "SKIPPED_NOT_INSTALLED" if status == SKIPPED_NOT_INSTALLED else status
        typer.echo(f"{profile.id:20s} {profile.model:24s} {flag}")


@app.command("bootstrap")
def bootstrap(
    model: str = typer.Option("qwen25_coder_3b", "--model"),
    team: str = typer.Option("five_agent", "--team"),
) -> None:
    _require_five_agent(team)
    profile = resolve_profile(model)
    status = availability(profile)
    if status != "installed":
        raise typer.BadParameter(f"{status}: {profile.model}")
    split = split_instances(load_all())
    result = bootstrap_solver(
        ROOT / "workspace" / "discovery" / profile.id,
        make_backend(profile),
        model=profile.model,
        instance=smoke_instance(1),
        temperatures=profile.temperatures,
        discovery=split["discovery"],
    )
    typer.echo(json_dumps(result))


@app.command("discover")
def discover(
    model: str = typer.Option("qwen25_coder_3b", "--model"),
    cycles: int = typer.Option(15, "--cycles"),
    team: str = typer.Option("five_agent", "--team"),
    campaign_id: str = typer.Option("discovery", "--campaign-id"),
) -> None:
    _require_five_agent(team)
    profile = resolve_profile(model)
    status = availability(profile)
    if status != "installed":
        raise typer.BadParameter(f"{status}: {profile.model}")
    workspace = ROOT / "workspace" / "discovery" / profile.id
    state = run_campaign(
        model=profile.model,
        backend=make_backend(profile),
        workspace=workspace,
        cycles=cycles,
        campaign_id=campaign_id,
        model_id=profile.id,
        temperatures=profile.temperatures,
    )
    typer.echo(json_dumps(state.__dict__))


@app.command("resume")
def resume(campaign_id: str = typer.Argument(...), extra_cycles: int = typer.Option(1, "--cycles")) -> None:
    candidates = [ROOT / "workspace" / "campaigns" / f"{campaign_id}.json"]
    for root_name in ("discovery", "repair"):
        folder = ROOT / "workspace" / root_name
        if folder.exists():
            candidates.extend(sorted(folder.glob(f"*/campaigns/{campaign_id}.json")))
    path = next((item for item in candidates if item.exists()), None)
    if path is None:
        raise typer.BadParameter(f"campaign not found: {campaign_id}")
    state = CampaignState.load(path)
    profile = resolve_profile(state.model_id or "qwen25_coder_3b")
    status = availability(profile)
    if status != "installed":
        raise typer.BadParameter(f"{status}: {profile.model}")
    workspace = path.parents[1]
    state = run_campaign(
        model=profile.model,
        backend=make_backend(profile),
        workspace=workspace,
        cycles=state.cycle + extra_cycles,
        campaign_id=campaign_id,
        model_id=profile.id,
        temperatures=profile.temperatures,
    )
    typer.echo(json_dumps(state.__dict__))


@app.command("evaluate")
def evaluate_cmd(
    solver_id: str = typer.Argument(...),
    fidelity: str = typer.Option("F1", "--fidelity"),
    partition: str = typer.Option("discovery", "--partition"),
) -> None:
    if partition == "heldout":
        raise typer.BadParameter("use the heldout command with --confirm")
    split = split_instances(load_all())
    if partition not in split:
        raise typer.BadParameter("partition must be discovery or confirmation")
    result = evaluate_fidelity(
        _solver_dir(solver_id), split[partition], fidelity, seeds=[0], limits=RunLimits()
    )
    typer.echo(json_dumps(result))


@app.command("benchmark-models")
def benchmark_models_cmd(
    config: Path = typer.Option(ROOT / "configs" / "experiments.yaml", "--config"),
) -> None:
    experiments = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    model_ids = list((experiments.get("model_comparison") or {}).get("model_ids") or [])
    rows = benchmark_models(model_ids=model_ids, workspace=ROOT / "workspace" / "model_benchmark")
    for row in rows:
        typer.echo(f"{row['model_id']}: {row.get('status')} feasible={row.get('feasible')}")


@app.command("export")
def export_cmd(
    solver_id: str = typer.Argument(...),
    output: Path = typer.Option(ROOT / "workspace" / "exports" / "final_solver", "--output"),
) -> None:
    export_solver(_solver_dir(solver_id), output)
    typer.echo(f"exported {output} (no LLM at runtime)")


@app.command("heldout")
def heldout(
    solver_id: str = typer.Argument(...),
    confirm: bool = typer.Option(False, "--confirm", help="Required. Discovery never uses RC2."),
) -> None:
    if not confirm:
        raise typer.BadParameter("held-out evaluation is final mode only; pass --confirm")
    payload = run_heldout(
        _solver_dir(solver_id),
        log_path=ROOT / "results" / "heldout" / f"{solver_id}.json",
    )
    typer.echo(json_dumps(payload))


def main() -> None:
    app()


if __name__ == "__main__":
    main()

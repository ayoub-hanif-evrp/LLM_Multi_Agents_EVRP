"""EvoCharge CLI — lean Schneider EVRPTW optimization entrypoints."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import orjson
import typer

from evocharge.config import resolve_project_root
from evocharge.data.contract import build_schneider_contract
from evocharge.logging_utils import setup_logging
from evocharge.system_info import collect_system_info

app = typer.Typer(no_args_is_help=True, add_completion=False)
baseline_app = typer.Typer(no_args_is_help=True, help="Construction + ALNS")
candidate_app = typer.Typer(no_args_is_help=True, help="LLM operator candidates")
evolve_app = typer.Typer(no_args_is_help=True, help="Operator evolution loop")
app.add_typer(baseline_app, name="baseline")
app.add_typer(candidate_app, name="candidate")
app.add_typer(evolve_app, name="evolve")


def _root() -> Path:
    return resolve_project_root()


def _default_instance(root: Path) -> Path:
    from evocharge.candidates.integration import ANCHORED_RELATIVE

    for base in (
        root / "dataset" / "schneider" / "raw_instances",
    ):
        for name in ANCHORED_RELATIVE:
            path = base / name
            if path.is_file():
                return path
        matches = sorted(base.glob("*C5.txt"))
        if matches:
            return matches[0]
    raise typer.BadParameter("No Schneider instance found under dataset/schneider/raw_instances")


@app.command("system-info")
def system_info_cmd(
    output: Path | None = typer.Option(None, help="Optional JSON output path"),
) -> None:
    """Hardware/software diagnostics (no model inference)."""
    info = collect_system_info(_root())
    text = orjson.dumps(info, option=orjson.OPT_INDENT_2).decode()
    typer.echo(text)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")


@app.command("build-contract")
def build_contract_cmd() -> None:
    """Build Schneider dataset contract from raw_instances."""
    root = _root()
    raw_dir = root / "dataset" / "schneider" / "raw_instances"
    files = sorted(raw_dir.glob("*.txt")) if raw_dir.is_dir() else []
    contract = build_schneider_contract(
        evidence_files=[str(raw_dir)] + [str(p) for p in files[:5]],
        n_instances=len(files),
    )
    out = root / "data" / "contracts" / "schneider_v1.0.json"
    contract.write_json(out)
    typer.echo(f"Wrote {out} n_instances={len(files)} hash={contract.contract_hash}")


@app.command("full-stack-run")
def full_stack_run(
    instance: Path | None = typer.Option(None, help="Schneider instance path"),
    candidate: str = typer.Option("m9b_main_20260728_seed_h1"),
    seed: int = typer.Option(2027),
    config: Path = typer.Option(Path("configs/schneider_main.yaml")),
    experiment_id: str | None = typer.Option(None),
) -> None:
    """Register a verified candidate into ALNS and compare vs baseline."""
    from evocharge.evaluation.fullstack import run_full_stack

    root = _root()
    cfg = config if config.is_absolute() else root / config
    inst = instance if instance is not None else _default_instance(root)
    if not Path(inst).is_absolute():
        inst = root / inst
    if not inst.is_file():
        raise typer.BadParameter(f"instance not found: {inst}")
    report = run_full_stack(
        project_root=root,
        instance_path=inst,
        candidate_id=candidate,
        seed=seed,
        config_path=cfg,
        experiment_id=experiment_id,
    )
    typer.echo(
        json.dumps(
            {
                "experiment_id": report["experiment_id"],
                "candidate_id": report["candidate_id"],
                "instance": report["instance"],
                "arms": report["arms"],
                "decision_gate": report["decision_gate"],
            },
            indent=2,
            sort_keys=True,
        )
    )


@baseline_app.command("construct")
def baseline_construct(
    config: Path = typer.Option(Path("configs/schneider_main.yaml")),
    instance: Path | None = typer.Option(None),
) -> None:
    """Construct an initial feasible solution."""
    import yaml

    from evocharge.data.schneider_parser import parse_schneider_file
    from evocharge.solver.construction import construct_initial_solution

    root = _root()
    raw = yaml.safe_load((config if config.is_absolute() else root / config).read_text(encoding="utf-8")) or {}
    inst_path = instance
    if inst_path is None:
        glob_pat = (raw.get("extras") or {}).get(
            "instance_glob", "dataset/schneider/raw_instances/*C5.txt"
        )
        matches = sorted(root.glob(glob_pat))
        if not matches:
            raise typer.BadParameter("No instance found; pass --instance")
        inst_path = matches[0]
    elif not Path(inst_path).is_absolute():
        inst_path = root / inst_path
    inst = parse_schneider_file(inst_path)
    result = construct_initial_solution(inst)
    summary = {
        "instance_id": inst.instance_id,
        "instance_path": str(inst_path),
        "feasible": result.feasible,
        "unserved": result.unserved,
        "n_routes": len(result.solution.routes) if result.solution else 0,
    }
    typer.echo(json.dumps(summary, indent=2, sort_keys=True))


@baseline_app.command("run")
def baseline_run(
    config: Path = typer.Option(Path("configs/schneider_main.yaml")),
    instance: Path | None = typer.Option(None),
    run_id: str | None = typer.Option(None),
) -> None:
    """Run deterministic ALNS baseline (no Ollama)."""
    import yaml

    from evocharge.data.schneider_parser import parse_schneider_file
    from evocharge.solver.alns import load_alns_config, run_alns

    root = _root()
    cfg_path = config if config.is_absolute() else root / config
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    alns_cfg = load_alns_config(raw)
    if "seed" in raw and "seed" not in (raw.get("alns") or {}):
        alns_cfg.seed = int(raw["seed"])
    inst_path = instance
    if inst_path is None:
        glob_pat = (raw.get("extras") or {}).get(
            "instance_glob", "dataset/schneider/raw_instances/*C5.txt"
        )
        matches = sorted(root.glob(glob_pat))
        if not matches:
            raise typer.BadParameter("No instance found; pass --instance")
        inst_path = matches[0]
    elif not Path(inst_path).is_absolute():
        inst_path = root / inst_path
    inst = parse_schneider_file(inst_path)
    rid = run_id or f"alns_{inst.instance_id}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
    out_dir = root / "artifacts" / "runs" / rid
    result = run_alns(
        inst,
        config=alns_cfg,
        run_dir=out_dir,
        run_id=rid,
        instance_path=str(inst_path),
        contract_path=root / "data" / "contracts" / "schneider_v1.0.json",
    )
    typer.echo(
        json.dumps(
            {
                "run_id": result.run_id,
                "feasible": result.feasible,
                "objective": result.objective.model_dump(),
                "iterations": result.iterations,
                "elapsed_seconds": result.elapsed_seconds,
                "summary": str(result.summary_path),
            },
            indent=2,
            sort_keys=True,
        )
    )


@candidate_app.command("generate")
def candidate_generate(
    scientist_report: Path = typer.Option(..., help="Scientist report JSON"),
    hypothesis_id: str = typer.Option(...),
    model: str = typer.Option("qwen3:4b"),
    config: Path = typer.Option(Path("configs/agents.yaml")),
    backend: str = typer.Option("ollama", help="ollama|mock|replay"),
    operator_type: str = typer.Option("plan_builder"),
    candidate_id: str | None = typer.Option(None),
) -> None:
    """Generate a bounded operator candidate."""
    from evocharge.agents.model_config import load_agents_config
    from evocharge.agents.ollama_client import check_ollama
    from evocharge.agents.schemas import ScientistReport
    from evocharge.candidates.pipeline import generate_candidate

    root = _root()
    cfg = load_agents_config(config if config.is_absolute() else root / config)
    cfg.backend = backend
    if backend == "ollama":
        health = check_ollama(cfg.ollama, model=model)
        smoke = health.get("smoke_test") or {}
        if not health.get("model_installed") or not smoke.get("ok"):
            typer.echo(json.dumps(health, indent=2, sort_keys=True))
            raise typer.Exit(code=1)

    report = ScientistReport.model_validate(
        json.loads(scientist_report.read_text(encoding="utf-8"))
    )
    summary = generate_candidate(
        project_root=root,
        scientist_report=report,
        hypothesis_id=hypothesis_id,
        config=cfg,
        model=model if backend == "ollama" else None,
        operator_type=operator_type,  # type: ignore[arg-type]
        candidate_id=candidate_id,
    )
    typer.echo(json.dumps(summary, indent=2, sort_keys=True))
    if summary.get("status") in {"STATIC_REJECTED", "DYNAMIC_REJECTED"}:
        raise typer.Exit(code=1)


@evolve_app.command("run")
def evolve_run(
    config: Path = typer.Option(Path("configs/schneider_main.yaml")),
    experiment_id: str | None = typer.Option(None),
    backend: str = typer.Option("structured"),
    generation_method: str = typer.Option("structured"),
) -> None:
    """Run operator evolution / population loop."""
    from evocharge.evolution.run import run_evolution

    root = _root()
    cfg_path = config if config.is_absolute() else root / config
    summary = run_evolution(
        project_root=root,
        config_path=cfg_path,
        experiment_id=experiment_id,
        backend=backend,
        generation_method=generation_method,
        freeze_path=None,
    )
    typer.echo(
        json.dumps(
            {
                "experiment_id": summary["experiment_id"],
                "freeze_hash": summary["freeze_hash"],
                "generation_method": summary.get("generation_method"),
                "success_flags": summary["success_flags"],
                "metrics": summary.get("metrics"),
                "archive_size": len(summary.get("archive") or []),
            },
            indent=2,
            sort_keys=True,
        )
    )


@app.callback()
def _main() -> None:
    setup_logging()


if __name__ == "__main__":
    app()

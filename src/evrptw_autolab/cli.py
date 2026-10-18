"""VoltForge CLI: validate data, list models, audit datasets."""
from __future__ import annotations

import json
from pathlib import Path

import typer

from evrptw_autolab.evaluation.fidelity import load_all, split_instances, write_split_manifest
from evrptw_autolab.llm.ollama import OllamaBackend
from evrptw_autolab.llm.registry import SKIPPED_NOT_INSTALLED, availability, list_profiles
from evrptw_autolab.problem.hashes import write_instance_hashes
from evrptw_autolab.problem.schneider import SCHNEIDER_ROOT, discover_instances

app = typer.Typer(no_args_is_help=True, add_completion=False)
models_app = typer.Typer(no_args_is_help=True, help="Inspect configured LLM model profiles.")
datasets_app = typer.Typer(no_args_is_help=True, help="Dataset registry and audit.")
components_app = typer.Typer(no_args_is_help=True, help="Component synthesis smoke (Track 2).")
baselines_app = typer.Typer(no_args_is_help=True, help="Classical and LLM baseline pilots.")
experiments_app = typer.Typer(no_args_is_help=True, help="Matched research campaigns.")
app.add_typer(models_app, name="models")
app.add_typer(datasets_app, name="datasets")
app.add_typer(components_app, name="components")
app.add_typer(baselines_app, name="baselines")
app.add_typer(experiments_app, name="experiments")
ROOT = Path(__file__).resolve().parents[2]


@experiments_app.command("expressions")
def experiments_expressions(
    fake: bool = typer.Option(True, "--fake/--ollama"),
    profile: str = typer.Option("qwen3_coder_30b", "--profile"),
) -> None:
    """Ask for one expression per component and report validation, without a campaign."""
    from evrptw_autolab.experiments.expression_probe import probe_expressions, write_probe
    from evrptw_autolab.llm.registry import FakeBackend

    if fake:
        backend = FakeBackend(
            {
                "routing": json.dumps(
                    {"component": "insertion_score", "expression": "delta_distance + 0.01 * due_time"}
                ),
                "charging": json.dumps({"component": "station_score", "expression": "detour"}),
                "search": json.dumps(
                    {"component": "removal_priority", "expression": "due_time + route_distance_share"}
                ),
            }
        )
        model = "fake"
    else:
        from evrptw_autolab.llm.ollama import OllamaBackend
        from evrptw_autolab.llm.registry import availability, make_backend, resolve_profile

        ollama = OllamaBackend()
        prof = resolve_profile(profile)
        if availability(prof, ollama) != "installed":
            typer.echo(f"SKIPPED profile {profile}")
            raise typer.Exit(code=0)
        backend = make_backend(prof, ollama_host=ollama.host)
        model = prof.model
    report = probe_expressions(backend, model=model)
    out = ROOT / "results" / "v2" / "probes" / f"expressions_{profile if not fake else 'fake'}.json"
    write_probe(report, out)
    typer.echo(json.dumps({**report, "path": str(out)}, indent=2))


@experiments_app.command("montoya-attribution")
def experiments_montoya_attribution() -> None:
    """Reproduce the recorded Montoya removal ablation and all eight subsets."""
    from evrptw_autolab.experiments.montoya_attribution import write_factorial

    out = write_factorial()
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    typer.echo(json.dumps({"out": str(out), "summary": summary}, indent=2))


@experiments_app.command("montoya-removal-replication")
def experiments_montoya_removal_replication() -> None:
    """Repeat the recorded removal policy on both development instances and seeds 7, 11, and 22."""
    from evrptw_autolab.experiments.montoya_attribution import write_removal_replication

    out = write_removal_replication()
    summary = json.loads((out / "removal_replication_summary.json").read_text(encoding="utf-8"))
    typer.echo(json.dumps({"out": str(out), "summary": summary}, indent=2))


@experiments_app.command("montoya-bundle-selection")
def experiments_montoya_bundle_selection() -> None:
    """Add recorded or random components only when no development pair gets worse."""
    from evrptw_autolab.experiments.bundle_selection import write_bundle_selection

    out = write_bundle_selection()
    summary = json.loads((out / "bundle_selection_summary.json").read_text(encoding="utf-8"))
    typer.echo(json.dumps({"out": str(out), "summary": summary}, indent=2))


@experiments_app.command("family-development-gate")
def experiments_family_development_gate(
    write_baseline: bool = typer.Option(False, "--write-baseline"),
) -> None:
    """Solve one development instance per family and compare with the frozen gate."""
    from evrptw_autolab.experiments.family_gate import judge_gate, load_baseline, measure_gate
    from evrptw_autolab.experiments.family_gate import write_baseline as save_baseline

    rows = measure_gate()
    if write_baseline:
        path = save_baseline(rows)
        typer.echo(json.dumps({"wrote": str(path), "rows": rows}, indent=2))
        return
    verdict = judge_gate(rows, load_baseline()["rows"])
    typer.echo(json.dumps({"verdict": verdict, "rows": rows}, indent=2))
    if not verdict["ok"]:
        raise typer.Exit(code=1)


@experiments_app.command("backbone-ablation")
def experiments_backbone_ablation() -> None:
    """Compare partial charging, route merge, and adaptive destroy on the development gate."""
    from evrptw_autolab.experiments.backbone_ablation import write_ablation

    path = write_ablation()
    summary = json.loads(path.read_text(encoding="utf-8"))
    brief = {
        "path": str(path),
        "adopted_variant": summary["adopted_variant"],
        "accepted_variants": summary["accepted_variants"],
        "decisions": {
            name: {
                "accepted": item["accepted"],
                "reason": item["reason"],
                "wins": item["wins"],
                "losses": item["losses"],
            }
            for name, item in summary["decisions"].items()
        },
    }
    typer.echo(json.dumps(brief, indent=2))


@experiments_app.command("campaign")
def experiments_campaign(
    fake: bool = typer.Option(True, "--fake/--ollama", help="FakeBackend (default) or local Ollama"),
    profile: str = typer.Option("qwen3_coder_30b", "--profile"),
    seed: int = typer.Option(7, "--seed"),
    max_instances: int = typer.Option(3, "--max-instances", help="Dev-panel cap; 0 = full panel"),
    time_limit_s: float = typer.Option(5.0, "--time-limit"),
    generations: int = typer.Option(2, "--generations"),
    max_llm_calls: int = typer.Option(24, "--max-llm-calls"),
    max_wall_s: float = typer.Option(600.0, "--max-wall"),
) -> None:
    """Matched classical vs single-agent vs five-agent vs evolution on the development panel.

    FakeBackend validates plumbing. Use --ollama for a real open-weight comparison.
    Never loads held-out instances.
    """
    from evrptw_autolab.experiments.campaign import CampaignConfig, run_research_campaign

    cfg = CampaignConfig(
        seed=seed,
        profile=profile,
        fake=fake,
        max_instances=None if max_instances <= 0 else max_instances,
        time_limit_s=time_limit_s,
        evolution_generations=generations,
        max_llm_calls=max_llm_calls,
        max_wall_s=max_wall_s,
    )
    payload = run_research_campaign(cfg)
    out = Path(str(payload["out_dir"]))
    typer.echo(
        json.dumps(
            {
                "out": str(out),
                "aggregate": payload["aggregate"],
                "wall_s": payload["wall_s"],
                "disclaimer": payload["disclaimer"],
                "paths": {"campaign": str(out / "campaign.json"), "rows": str(out / "rows.jsonl")},
            },
            indent=2,
        )
    )


@baselines_app.command("pilot")
def baselines_pilot(
    seed: int = typer.Option(7, "--seed"),
    seeds: str = typer.Option(
        "",
        "--seeds",
        help="Comma-separated seeds (overrides --seed), e.g. 7,11,22",
    ),
) -> None:
    """Run the human-authored classical solver on the five-family development panel."""
    from evrptw_autolab.baselines.classical_pilot import run_classical_pilot

    seed_list = [int(x.strip()) for x in seeds.split(",") if x.strip()] if seeds else None
    result = run_classical_pilot(
        seed=seed,
        seeds=seed_list,
        out_dir=ROOT / "results" / "v2" / "baselines" / "classical",
    )
    typer.echo(
        json.dumps(
            {
                "n": result["n"],
                "seeds": result.get("seeds"),
                "aggregate": result["aggregate"],
                "paths": result["paths"],
            },
            indent=2,
        )
    )


@app.command("validate-v2")
def validate_v2() -> None:
    """Offline mathematical / parser / reference checks (no Ollama)."""
    import subprocess
    import sys

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/test_evaluator_v2.py",
        "tests/test_dataset_parsers.py",
        "tests/test_v2_datasets_and_types.py",
        "tests/test_component_interpreter.py",
    ]
    raise typer.Exit(code=subprocess.call(cmd, cwd=ROOT))


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


@models_app.command("smoke")
def models_smoke(
    model: str = typer.Option(..., "--model", help="Exact Ollama model tag, e.g. qwen3-coder:30b"),
) -> None:
    """Fast capability smoke: server up, model installed, /api/show details."""
    ollama = OllamaBackend()
    report = ollama.capability_smoke(model)
    typer.echo(report)


@datasets_app.command("audit")
def datasets_audit(
    write_manifest: bool = typer.Option(
        True, "--write-manifest/--no-write-manifest", help="Write results/v2/manifests/dataset_audit.json"
    ),
) -> None:
    """Enumerate and hash all five benchmark families; validate Schneider via legacy loader."""
    from evrptw_autolab.problem.datasets.registry import audit_all, write_audit_manifest

    audits = audit_all()
    for audit in audits:
        typer.echo(
            f"{audit.family_id:10s} exists={audit.folder_exists} "
            f"raw={audit.raw_file_count:4d} instances={audit.instance_file_count:4d} "
            f"status={audit.parse_status} - {audit.parse_note}"
        )
        for warning in audit.warnings[:3]:
            typer.echo(f"  warning: {warning}")
    if write_manifest:
        path = write_audit_manifest(audits, ROOT / "results" / "v2" / "manifests" / "dataset_audit.json")
        typer.echo(f"manifest={path}")


@components_app.command("smoke")
def components_smoke(
    fake: bool = typer.Option(True, "--fake/--ollama", help="Use FakeBackend (default) or local Ollama"),
    profile: str = typer.Option("qwen3_coder_30b", "--profile", help="Ollama profile id when --ollama"),
    seed: int = typer.Option(0, "--seed"),
) -> None:
    """Cheap end-to-end component synthesis on Schneider micro_g2 (no long campaign)."""
    from evrptw_autolab.components.interfaces import DEFAULT_SOURCES
    from evrptw_autolab.components.run import synthesize_components
    from evrptw_autolab.llm.registry import FakeBackend, availability, make_backend, resolve_profile
    from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
    from evrptw_autolab.problem.micro import micro_g2_needs_charge

    spec = load_schneider_v2(micro_g2_needs_charge().metadata["source_path"])
    if fake:
        backend = FakeBackend(
            {
                "architect": json.dumps(
                    {
                        "summary": "smoke",
                        "components": ["insertion_score", "station_score", "removal_priority"],
                        "risks": [],
                        "success_criteria": ["feasible"],
                        "variant_notes": "micro",
                    }
                ),
                "routing": json.dumps(
                    {
                        "component": "insertion_score",
                        "owner_role": "routing",
                        "code": DEFAULT_SOURCES["insertion_score"],
                        "rationale": "r",
                        "mechanism": "m",
                    }
                ),
                "charging": json.dumps(
                    {
                        "component": "station_score",
                        "owner_role": "charging",
                        "code": DEFAULT_SOURCES["station_score"],
                        "rationale": "r",
                        "mechanism": "m",
                    }
                ),
                "search": json.dumps(
                    {
                        "component": "removal_priority",
                        "owner_role": "search",
                        "code": DEFAULT_SOURCES["removal_priority"],
                        "rationale": "r",
                        "mechanism": "m",
                    }
                ),
                "critic": json.dumps(
                    {"verdict": "ACCEPT", "reason": "smoke", "next_component": "none"}
                ),
            }
        )
        model = "fake"
    else:
        from evrptw_autolab.llm.ollama import OllamaBackend

        ollama = OllamaBackend()
        prof = resolve_profile(profile)
        status = availability(prof, ollama)
        if status != "installed":
            typer.echo(f"SKIPPED: profile {profile} status={status}")
            raise typer.Exit(code=0)
        backend = make_backend(prof, ollama_host=ollama.host)
        model = prof.model
    out_dir = ROOT / "results" / "v2" / "runs" / f"component_smoke_seed{seed}"
    result = synthesize_components(
        spec, backend, model=model, seed=seed, time_limit_s=5.0, work_dir=out_dir
    )
    keys = (
        "feasible",
        "vehicles",
        "distance",
        "llm_calls",
        "llm_tokens",
        "genuine_llm_components",
        "default_heuristic_count",
        "critic_verdict",
        "wall_s",
        "bundle_dir",
        "model",
    )
    typer.echo(json.dumps({k: result[k] for k in keys if k in result}, indent=2))


def main() -> None:
    app()


if __name__ == "__main__":
    main()

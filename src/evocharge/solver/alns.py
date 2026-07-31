"""Deterministic ALNS baseline with profiling, checkpoints, and resume (no LLM)."""

from __future__ import annotations

import json
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from evocharge.config import resolve_project_root
from evocharge.domain.instance import Instance
from evocharge.domain.objective import ObjectiveVector
from evocharge.domain.solution import Solution
from evocharge.operators.api import OperatorContext
from evocharge.operators.handcrafted.destroy import DESTROY_OPERATORS
from evocharge.operators.handcrafted.local_search import local_search
from evocharge.operators.handcrafted.repair import REPAIR_OPERATORS
from evocharge.solver.acceptance import accept_candidate, cool
from evocharge.solver.charging_repair import ChargingRepairCache, RepairBounds
from evocharge.solver.construction import construct_initial_solution
from evocharge.solver.experiment import write_experiment_manifest
from evocharge.solver.feasibility import evaluate_feasibility, evaluate_objective
from evocharge.solver.memory import memory_dict
from evocharge.solver.profiling import Profiler
from evocharge.solver.propagation import propagate_route
from evocharge.solver.selection import AdaptiveWeights
from evocharge.solver.trace import TraceWriter


@dataclass
class ALNSConfig:
    seed: int = 2027
    max_iterations: int = 100
    time_limit_seconds: float = 30.0
    # When True, stop only on max_iterations / memory (ignore wall-clock time limit).
    iteration_budget_only: bool = False
    destroy_fraction: float = 0.25
    initial_temperature: float = 5.0
    cooling_rate: float = 0.995
    reaction_factor: float = 0.2
    local_search_every: int = 20
    local_search_max_moves: int = 30
    checkpoint_every: int = 10
    reward_best: float = 9.0
    reward_improve: float = 3.0
    reward_accept: float = 1.0
    memory_limit_mb: float = 4096.0
    max_workers: int = 4
    resume: bool = False
    repair_max_stations_between: int = 1
    repair_max_station_candidates: int = 8
    repair_max_attempts: int = 400
    repair_timeout_seconds: float = 2.0
    repair_enable_two_station: bool = False
    cache_max_entries: int = 10_000


@dataclass
class ALNSResult:
    run_id: str
    solution: Solution
    objective: ObjectiveVector
    feasible: bool
    seed: int
    iterations: int
    elapsed_seconds: float
    time_to_best: float
    trace_path: Path
    summary_path: Path
    cache_hits: int
    cache_misses: int
    profile: dict[str, Any] = field(default_factory=dict)
    peak_rss_mb: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


def _obj_dict(obj: ObjectiveVector) -> dict[str, Any]:
    return obj.model_dump()


def _solution_from_routes(instance: Instance, routes_nodes: list[list[str]]) -> Solution:
    routes = [
        propagate_route(instance, tuple(nodes), vehicle_index=i)
        for i, nodes in enumerate(routes_nodes)
    ]
    return Solution(routes=tuple(routes))


def _serialize_rng(rng: random.Random) -> dict[str, Any]:
    state = rng.getstate()
    return {
        "version": state[0],
        "data": list(state[1]),
        "gauss": state[2],
    }


def _restore_rng(rng: random.Random, payload: dict[str, Any] | None) -> None:
    if not payload:
        return
    rng.setstate((payload["version"], tuple(payload["data"]), payload["gauss"]))


def _write_checkpoint(
    run_dir: Path,
    *,
    iteration: int,
    temperature: float,
    time_to_best: float,
    select_rng: random.Random,
    destroy_rng: random.Random,
    repair_rng: random.Random,
    accept_rng: random.Random,
    destroy_w: AdaptiveWeights,
    repair_w: AdaptiveWeights,
    current: Solution,
    best: Solution,
    best_obj: ObjectiveVector,
    feasible: bool,
) -> None:
    payload = {
        "iteration": iteration,
        "temperature": temperature,
        "time_to_best": time_to_best,
        "destroy_weights": destroy_w.weights,
        "repair_weights": repair_w.weights,
        "current_routes": [list(r.node_ids) for r in current.routes],
        "best_routes": [list(r.node_ids) for r in best.routes],
        "objective": best_obj.model_dump(),
        "feasible": feasible,
        "rng_streams": {
            "select": _serialize_rng(select_rng),
            "destroy": _serialize_rng(destroy_rng),
            "repair": _serialize_rng(repair_rng),
            "accept": _serialize_rng(accept_rng),
        },
        # Legacy single-stream field for older resume tools
        "rng_state": _serialize_rng(select_rng),
    }
    tmp = run_dir / "checkpoint.json.tmp"
    final = run_dir / "checkpoint.json"
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(final)


def _load_checkpoint(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Checkpoint must be a JSON object: {path}")
    return payload


def run_alns(
    instance: Instance,
    *,
    config: ALNSConfig,
    run_dir: Path,
    run_id: str,
    initial: Solution | None = None,
    instance_path: str | None = None,
    contract_path: Path | None = None,
    destroy_operators: dict[str, Any] | None = None,
    repair_operators: dict[str, Any] | None = None,
    destroy_weight_overrides: dict[str, float] | None = None,
) -> ALNSResult:
    destroy_ops = destroy_operators or DESTROY_OPERATORS
    repair_ops = repair_operators or REPAIR_OPERATORS
    run_dir.mkdir(parents=True, exist_ok=True)
    profiler = Profiler()
    cache = ChargingRepairCache(max_entries=config.cache_max_entries)
    bounds = RepairBounds(
        max_stations_between=config.repair_max_stations_between,
        max_station_candidates=config.repair_max_station_candidates,
        max_attempts=config.repair_max_attempts,
        timeout_seconds=config.repair_timeout_seconds,
        enable_two_station=config.repair_enable_two_station,
    )
    ctx = OperatorContext(
        instance=instance,
        cache=cache,
        destroy_fraction=config.destroy_fraction,
        repair_bounds=bounds,
        profiler=profiler,
    )

    # Separate deterministic streams so unused draws inside one operator
    # cannot desynchronize selection / acceptance for control comparisons.
    select_rng = random.Random(config.seed)
    destroy_rng = random.Random(config.seed + 1_000_003)
    repair_rng = random.Random(config.seed + 2_000_003)
    accept_rng = random.Random(config.seed + 3_000_003)
    destroy_names = sorted(destroy_ops.keys())
    repair_names = sorted(repair_ops.keys())
    destroy_w = AdaptiveWeights(names=destroy_names, reaction=config.reaction_factor)
    repair_w = AdaptiveWeights(names=repair_names, reaction=config.reaction_factor)
    if destroy_weight_overrides:
        for name, weight in destroy_weight_overrides.items():
            if name in destroy_w.weights:
                destroy_w.weights[name] = float(weight)

    temperature = config.initial_temperature
    time_to_best = 0.0
    it = 0
    peak_rss = memory_dict()["rss_mb"]

    ckpt = _load_checkpoint(run_dir / "checkpoint.json") if config.resume else None
    if ckpt is not None:
        it = int(ckpt["iteration"])
        temperature = float(ckpt["temperature"])
        time_to_best = float(ckpt.get("time_to_best", 0.0))
        streams = ckpt.get("rng_streams") or {}
        if streams:
            _restore_rng(select_rng, streams.get("select"))
            _restore_rng(destroy_rng, streams.get("destroy"))
            _restore_rng(repair_rng, streams.get("repair"))
            _restore_rng(accept_rng, streams.get("accept"))
        else:
            # Legacy checkpoints: restore single stream into all (best-effort)
            _restore_rng(select_rng, ckpt.get("rng_state"))
            _restore_rng(destroy_rng, ckpt.get("rng_state"))
            _restore_rng(repair_rng, ckpt.get("rng_state"))
            _restore_rng(accept_rng, ckpt.get("rng_state"))
        destroy_w.weights.update(ckpt.get("destroy_weights", {}))
        repair_w.weights.update(ckpt.get("repair_weights", {}))
        current = _solution_from_routes(instance, ckpt["current_routes"])
        best = _solution_from_routes(instance, ckpt["best_routes"])
        with profiler.section("feasibility"):
            cur_report = evaluate_feasibility(instance, current)
            cur_obj = evaluate_objective(instance, current, cur_report)
            best_report = evaluate_feasibility(instance, best)
            best_obj = evaluate_objective(instance, best, best_report)
        resumed = True
    else:
        if initial is None:
            with profiler.section("construction"):
                constructed = construct_initial_solution(
                    instance, cache=cache, bounds=bounds, profiler=profiler
                )
            current = constructed.solution or Solution(routes=())
        else:
            current = initial
        with profiler.section("feasibility"):
            cur_report = evaluate_feasibility(instance, current)
            cur_obj = evaluate_objective(instance, current, cur_report)
        best = current
        best_obj = cur_obj
        best_report = cur_report
        resumed = False

    # Truncate trace on fresh run; append on resume
    trace_path = run_dir / "events.jsonl.gz"
    if not resumed and trace_path.exists():
        trace_path.unlink()
    trace = TraceWriter(trace_path)
    trace.log(
        {
            "event": "start" if not resumed else "resume",
            "seed": config.seed,
            "instance_id": instance.instance_id,
            "config": asdict(config),
            "initial_objective": _obj_dict(cur_obj),
            "initial_feasible": cur_report.feasible,
            "resumed_from_iteration": it if resumed else None,
        }
    )

    root = resolve_project_root()
    write_experiment_manifest(
        run_dir,
        config={"alns": asdict(config)},
        contract_path=contract_path
        or (root / "data" / "contracts" / "schneider_v1.0.json"),
        objective_definition=best_obj.definition,
        seed=config.seed,
        instance_id=instance.instance_id,
        instance_path=instance_path,
        project_root=root,
    )
    (run_dir / "config.yaml").write_text(
        yaml.safe_dump({"alns": asdict(config), "instance_id": instance.instance_id}),
        encoding="utf-8",
    )

    t0 = time.perf_counter()
    stop_reason = "completed"
    while it < config.max_iterations:
        if (
            not config.iteration_budget_only
            and (time.perf_counter() - t0) >= config.time_limit_seconds
        ):
            stop_reason = "time_limit"
            break
        mem = memory_dict()
        peak_rss = max(peak_rss, mem["rss_mb"])
        if mem["rss_mb"] > config.memory_limit_mb:
            stop_reason = "memory_limit"
            break

        it += 1
        with profiler.section("operators"):
            d_name = destroy_w.select(select_rng)
            r_name = repair_w.select(select_rng)
            # Always advance parent streams once per iteration (slot-invariant).
            d_child = random.Random(destroy_rng.randrange(2**31))
            r_child = random.Random(repair_rng.randrange(2**31))
            destroyed = destroy_ops[d_name](current, ctx, d_child)
            repaired = repair_ops[r_name](
                destroyed.solution, destroyed.removed_customers, ctx, r_child
            )
            candidate = repaired.solution
            if config.local_search_every > 0 and it % config.local_search_every == 0:
                with profiler.section("local_search"):
                    candidate = local_search(
                        instance,
                        candidate,
                        cache=cache,
                        max_moves=config.local_search_max_moves,
                        bounds=bounds,
                    )

        with profiler.section("feasibility"):
            cand_report = evaluate_feasibility(instance, candidate)
            cand_obj = evaluate_objective(instance, candidate, cand_report)
        accepted = accept_candidate(
            cur_obj, cand_obj, temperature=temperature, rng=accept_rng
        )

        reward = 0.0
        if accepted:
            improved = cand_obj.as_tuple() < cur_obj.as_tuple()
            current = candidate
            cur_obj = cand_obj
            cur_report = cand_report
            reward = config.reward_accept
            if cand_obj.as_tuple() < best_obj.as_tuple():
                best = candidate
                best_obj = cand_obj
                best_report = cand_report
                time_to_best = time.perf_counter() - t0
                reward = config.reward_best
            elif improved:
                reward = config.reward_improve

        destroy_w.reward(d_name, reward)
        repair_w.reward(r_name, reward)
        if it % 10 == 0:
            destroy_w.adapt()
            repair_w.adapt()

        temperature = cool(temperature, config.cooling_rate)
        trace.log(
            {
                "event": "iteration",
                "iteration": it,
                "destroy": d_name,
                "repair": r_name,
                "removed": list(destroyed.removed_customers),
                "accepted": accepted,
                "temperature": temperature,
                "current_objective": _obj_dict(cur_obj),
                "candidate_objective": _obj_dict(cand_obj),
                "best_objective": _obj_dict(best_obj),
                "candidate_feasible": cand_report.feasible,
                "feasibility_failures": cand_report.violation_count,
                "insertion_rejections": list(repaired.rejection_reasons),
                "unserved_after_repair": list(repaired.unserved),
                "cache_hits": cache.hits,
                "cache_misses": cache.misses,
                "rss_mb": mem["rss_mb"],
            }
        )

        if config.checkpoint_every and it % config.checkpoint_every == 0:
            _write_checkpoint(
                run_dir,
                iteration=it,
                temperature=temperature,
                time_to_best=time_to_best,
                select_rng=select_rng,
                destroy_rng=destroy_rng,
                repair_rng=repair_rng,
                accept_rng=accept_rng,
                destroy_w=destroy_w,
                repair_w=repair_w,
                current=current,
                best=best,
                best_obj=best_obj,
                feasible=best_report.feasible,
            )

    elapsed = time.perf_counter() - t0
    with profiler.section("feasibility"):
        final_report = evaluate_feasibility(instance, best)
        final_obj = evaluate_objective(instance, best, final_report)
    peak_rss = max(peak_rss, memory_dict()["rss_mb"])

    _write_checkpoint(
        run_dir,
        iteration=it,
        temperature=temperature,
        time_to_best=time_to_best,
        select_rng=select_rng,
        destroy_rng=destroy_rng,
        repair_rng=repair_rng,
        accept_rng=accept_rng,
        destroy_w=destroy_w,
        repair_w=repair_w,
        current=current,
        best=best,
        best_obj=final_obj,
        feasible=final_report.feasible,
    )
    trace.log(
        {
            "event": "end",
            "iterations": it,
            "elapsed_seconds": elapsed,
            "time_to_best": time_to_best,
            "best_objective": _obj_dict(final_obj),
            "best_feasible": final_report.feasible,
            "cache": cache.stats(),
            "profile": profiler.snapshot(),
            "peak_rss_mb": peak_rss,
            "stop_reason": stop_reason,
        }
    )
    trace.close()

    profile = profiler.snapshot()
    summary = {
        "run_id": run_id,
        "instance_id": instance.instance_id,
        "instance_path": instance_path,
        "seed": config.seed,
        "iterations": it,
        "elapsed_seconds": elapsed,
        "time_to_best": time_to_best,
        "feasible": final_report.feasible,
        "objective": _obj_dict(final_obj),
        "violation_count": final_report.violation_count,
        "cache_hits": cache.hits,
        "cache_misses": cache.misses,
        "cache": cache.stats(),
        "n_routes": len(best.routes),
        "profile": profile,
        "peak_rss_mb": peak_rss,
        "stop_reason": stop_reason,
        "resumed": resumed,
        "ollama_calls": 0,
    }
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return ALNSResult(
        run_id=run_id,
        solution=best,
        objective=final_obj,
        feasible=final_report.feasible,
        seed=config.seed,
        iterations=it,
        elapsed_seconds=elapsed,
        time_to_best=time_to_best,
        trace_path=trace.path,
        summary_path=summary_path,
        cache_hits=cache.hits,
        cache_misses=cache.misses,
        profile=profile,
        peak_rss_mb=peak_rss,
        metadata={"report": final_report.model_dump(), "stop_reason": stop_reason},
    )


def load_alns_config(raw: dict[str, Any]) -> ALNSConfig:
    block = raw.get("alns", raw)
    known = set(ALNSConfig.__dataclass_fields__)
    return ALNSConfig(**{k: v for k, v in block.items() if k in known})

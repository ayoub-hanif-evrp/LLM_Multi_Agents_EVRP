"""Experiment B campaign runner (post pilot freeze).

Uses the same structured synthesis loop as the pilot with campaign_profiles.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_structured_pilot import run_one  # noqa: E402


def _config() -> dict:
    return yaml.safe_load((ROOT / "configs" / "experiments.yaml").read_text(encoding="utf-8")) or {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--ablation", default="full")
    parser.add_argument(
        "--seeds",
        default="",
        help="Comma-separated seeds (default: pilot seeds)",
    )
    args = parser.parse_args()
    cfg = _config()
    block = cfg.get("structured_synthesis") or {}
    pilot = block.get("pilot") or {}
    profiles = list(block.get("campaign_profiles") or pilot.get("profiles") or [])
    if args.seeds:
        seeds = [int(x) for x in args.seeds.split(",") if x.strip()]
    else:
        seeds = [int(s) for s in (pilot.get("seeds") or [11, 22, 33])]
    if args.all:
        for profile_id in profiles:
            for seed in seeds:
                run_one(str(profile_id), seed, cfg, ablation=args.ablation)
        return
    if not args.profile or not args.seed:
        raise SystemExit("pass --all or both --profile and --seed")
    run_one(args.profile, args.seed, cfg, ablation=args.ablation)


if __name__ == "__main__":
    main()

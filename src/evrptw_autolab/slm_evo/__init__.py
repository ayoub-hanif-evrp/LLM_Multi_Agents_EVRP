"""SLM-Evo package."""

from evrptw_autolab.slm_evo.patch_apply import apply_ops, apply_proposal, parse_proposal_json

__all__ = ["apply_ops", "apply_proposal", "parse_proposal_json", "run_slm_evo"]


def __getattr__(name: str):
    if name == "run_slm_evo":
        from evrptw_autolab.slm_evo.evolve import run_slm_evo

        return run_slm_evo
    raise AttributeError(name)

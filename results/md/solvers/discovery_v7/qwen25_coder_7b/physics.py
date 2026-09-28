"""Local import shim for generated solvers that use `from physics import ...`."""
from evrptw_autolab.problem.physics import (  # noqa: F401
    distance,
    energy_required,
    full_recharge,
    propagate_route,
    travel_time,
)

"""Static detection of hardcoded instance identities (Milestone 9A)."""

from __future__ import annotations

import ast
import re

_ENTITY_ID_RE = re.compile(r"^[CDS]\d+$")
_CUSTOMER_RE = re.compile(r"^C\d+$")
_STATION_RE = re.compile(r"^S\d+$")


def _is_entity_literal(value: object) -> bool:
    return isinstance(value, str) and bool(_ENTITY_ID_RE.match(value))


def detect_hardcoded_identities(source: str) -> list[str]:
    """Return error codes for hardcoded customer/station/position assumptions."""
    errors: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return errors

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _CUSTOMER_RE.match(node.value):
                errors.append(f"hardcoded_customer_id:{node.value}")
            elif _STATION_RE.match(node.value):
                errors.append(f"hardcoded_station_id:{node.value}")
            elif re.match(r"^D\d+$", node.value):
                errors.append(f"hardcoded_depot_id:{node.value}")

        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
            lo = node.slice.lower
            hi = node.slice.upper
            if isinstance(lo, ast.Constant) and isinstance(hi, ast.Constant):
                if isinstance(lo.value, int) and isinstance(hi.value, int):
                    errors.append(f"fixed_route_position_slice:[{lo.value}:{hi.value}]")

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fname = node.func.id
            if fname in {
                "plan_customer_removal",
                "plan_regret_reinsertion",
                "plan_greedy_reinsertion",
            }:
                if node.args:
                    arg0 = node.args[0]
                    if isinstance(arg0, (ast.List, ast.Tuple)):
                        for elt in arg0.elts:
                            if isinstance(elt, ast.Constant) and _is_entity_literal(
                                elt.value
                            ):
                                errors.append(
                                    f"hardcoded_plan_argument:{fname}:{elt.value!s}"
                                )
            if fname == "plan_station_replacement":
                for arg in list(node.args)[:3]:
                    if isinstance(arg, ast.Constant) and _is_entity_literal(arg.value):
                        errors.append(
                            f"hardcoded_plan_argument:{fname}:{arg.value!s}"
                        )
                for kw in node.keywords:
                    if kw.arg in {
                        "old_station_id",
                        "new_station_id",
                        "station_id",
                    } and isinstance(kw.value, ast.Constant):
                        if _is_entity_literal(kw.value.value):
                            errors.append(
                                f"hardcoded_plan_argument:{fname}:{kw.value.value!s}"
                            )
            if fname == "plan_segment_removal":
                # Detect start_index=0, end_index=1 style kwargs/constants
                consts: list[int] = []
                for arg in node.args[1:3]:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, int):
                        consts.append(arg.value)
                kw_map = {
                    kw.arg: kw.value
                    for kw in node.keywords
                    if kw.arg in {"start_index", "end_index"}
                }
                for key in ("start_index", "end_index"):
                    val = kw_map.get(key)
                    if isinstance(val, ast.Constant) and isinstance(val.value, int):
                        consts.append(val.value)
                if consts == [0, 1] or (
                    len(consts) >= 2 and consts[0] == 0 and consts[1] == 1
                ):
                    errors.append("fixed_depot_segment_slice:[0:1]")

    # Semantic API misuse: enumerate station replacements without ranking stations first
    # (passing a customer id into station_id is a common LLM failure mode).
    src_l = source
    if "enumerate_feasible_station_replacements" in src_l and "rank_stations_by_detour" not in src_l:
        errors.append("station_enumerate_without_rank_stations_by_detour")

    return sorted(set(errors))

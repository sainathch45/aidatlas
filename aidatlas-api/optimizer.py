"""Constrained resource-dispatch optimizer for ai_drafted crises, using
Google OR-Tools (CP-SAT) -- a real solved optimization, not a sorted
ranking. Two real signals adjust the model beyond raw need_score:

  - network_multiplier: a district that sits on the real road corridor
    to other high-need districts (computed from Google Routes API, see
    data/fetch_road_chokepoints.py) gets a priority boost, since
    delivering there has a network effect beyond its own population.
  - access_factor: a district with significant live radar-measured
    flood extent has its deliverable capacity capped lower, since
    standing floodwater genuinely limits how much a truck convoy can
    move through -- never to zero (airlift/boat delivery stays
    possible), floored at 0.3.

No ML, no training -- a deterministic constraint solver, the correct
tool for "split a limited real resource pool under real constraints,"
not an approximation of one.
"""

import math

from ortools.sat.python import cp_model

CHOKEPOINT_WEIGHT = 0.15  # priority boost per other district this one gates access to
FLOOD_ACCESS_FLOOR = 0.3  # a badly flooded district can still receive at least this fraction of the per-district cap


def network_multiplier(district: dict) -> float:
    chokepoint = (district.get("context") or {}).get("chokepoint")
    gated_count = len(chokepoint["chokepoint_for"]) if chokepoint else 0
    return 1 + CHOKEPOINT_WEIGHT * gated_count


def access_factor(district: dict) -> float:
    flood = (district.get("context") or {}).get("flood_extent")
    if not flood:
        return 1.0
    pct = flood["flooded_area_pct_live"] / 100
    return max(FLOOD_ACCESS_FLOOR, 1 - pct)


def optimize_dispatch(districts: list[dict], capacity_units: int) -> dict[str, dict]:
    """districts: the normalized district dicts already used throughout
    main.py (admin_code, need_score, context...). Returns
    {admin_code: {"units_allocated", "network_multiplier", "access_factor"}}.
    """
    if capacity_units <= 0 or not districts:
        return {
            d["admin_code"]: {"units_allocated": 0, "network_multiplier": 1.0, "access_factor": 1.0}
            for d in districts
        }

    max_per_district = max(1, math.ceil(capacity_units / 2.5))

    model = cp_model.CpModel()
    x = {}
    weights = {}
    access = {}
    for d in districts:
        code = d["admin_code"]
        nm = network_multiplier(d)
        af = access_factor(d)
        weights[code] = nm
        access[code] = af
        cap_d = max(0, min(max_per_district, capacity_units, math.floor(max_per_district * af)))
        x[code] = model.NewIntVar(0, cap_d, f"x_{code}")

    model.Add(sum(x.values()) <= capacity_units)
    model.Maximize(
        sum(int(d["need_score"] * weights[d["admin_code"]] * 100) * x[d["admin_code"]] for d in districts)
    )

    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # Degrade gracefully rather than 500 -- the rest of the pipeline
        # (need-ranked priority list) still works without a solved plan.
        return {
            d["admin_code"]: {"units_allocated": 0, "network_multiplier": weights[d["admin_code"]], "access_factor": access[d["admin_code"]]}
            for d in districts
        }

    return {
        d["admin_code"]: {
            "units_allocated": solver.Value(x[d["admin_code"]]),
            "network_multiplier": round(weights[d["admin_code"]], 2),
            "access_factor": round(access[d["admin_code"]], 2),
        }
        for d in districts
    }

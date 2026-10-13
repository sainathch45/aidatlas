"""Parali Setu matching & pricing engine.

Solves the live farmer-listing <-> company-demand matching problem as a
transportation LP: maximize total payout to farmers, subject to each
listing's own quantity and each demand's quantity limits, with crop/
product match and quality-grade eligibility as hard constraints.

Gemini never touches this file (PRD docs/PARALI_SETU_PRD.md, Section 9 /
13). Every price and quantity a farmer or company is shown comes from
here. Re-run this on every new listing, demand change, or negotiation
counter-offer -- it's cheap enough to call live, not batched.
"""
from __future__ import annotations

from dataclasses import dataclass
from ortools.linear_solver import pywraplp

QUALITY_GRADES = ("unknown", "dry", "wet", "mixed")


@dataclass(frozen=True)
class Listing:
    id: str
    farmer_id: str
    quantity_kg: float
    crop_type: str
    quality_grade: str = "unknown"


@dataclass(frozen=True)
class Demand:
    id: str
    company_id: str
    crop_type: str
    quantity_needed_kg: float
    price_offer_per_kg: float
    accepted_quality_grades: tuple[str, ...] = QUALITY_GRADES


@dataclass(frozen=True)
class MatchResult:
    listing_id: str
    demand_id: str
    farmer_id: str
    company_id: str
    matched_kg: float
    price_agreed_per_kg: float


def _eligible(listing: Listing, demand: Demand) -> bool:
    if listing.crop_type != demand.crop_type:
        return False
    return listing.quality_grade in demand.accepted_quality_grades


def solve_matches(listings: list[Listing], demands: list[Demand]) -> list[MatchResult]:
    """Maximize total farmer payout across every eligible listing/demand pair.

    A listing or a demand can be split across more than one match if that
    raises total payout; neither is matched below zero or above its own
    remaining quantity. Returns an empty list (never raises) if nothing is
    eligible or the model is infeasible -- callers show "no match yet",
    not an error.
    """
    solver = pywraplp.Solver.CreateSolver("GLOP")
    if solver is None:
        raise RuntimeError("OR-Tools GLOP backend unavailable")

    pairs = [
        (listing, demand)
        for listing in listings
        for demand in demands
        if _eligible(listing, demand)
    ]
    if not pairs:
        return []

    flow = {
        (listing.id, demand.id): solver.NumVar(
            0, solver.infinity(), f"flow_{listing.id}_{demand.id}"
        )
        for listing, demand in pairs
    }

    for listing in listings:
        vars_for_listing = [
            flow[(l.id, d.id)] for l, d in pairs if l.id == listing.id
        ]
        if vars_for_listing:
            solver.Add(sum(vars_for_listing) <= listing.quantity_kg)

    for demand in demands:
        vars_for_demand = [
            flow[(l.id, d.id)] for l, d in pairs if d.id == demand.id
        ]
        if vars_for_demand:
            solver.Add(sum(vars_for_demand) <= demand.quantity_needed_kg)

    objective = solver.Objective()
    for listing, demand in pairs:
        objective.SetCoefficient(flow[(listing.id, demand.id)], demand.price_offer_per_kg)
    objective.SetMaximization()

    status = solver.Solve()
    if status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        return []

    results = []
    for listing, demand in pairs:
        qty = flow[(listing.id, demand.id)].solution_value()
        if qty > 1e-6:
            results.append(
                MatchResult(
                    listing_id=listing.id,
                    demand_id=demand.id,
                    farmer_id=listing.farmer_id,
                    company_id=demand.company_id,
                    matched_kg=round(qty, 2),
                    price_agreed_per_kg=demand.price_offer_per_kg,
                )
            )
    return results


def apply_negotiation(
    listings: list[Listing],
    demands: list[Demand],
    demand_id: str,
    new_price_offer_per_kg: float,
) -> list[MatchResult]:
    """Re-solve with one demand's price bumped by a counter-offer (PRD 8.1.7).

    Gemini parses the farmer's or company's natural-language counter-offer
    into this numeric delta elsewhere; this function still does the only
    arithmetic and the only re-matching. Returns the new full match set,
    not a diff -- callers compare against the prior result to describe
    what changed.
    """
    updated = [
        Demand(
            id=d.id,
            company_id=d.company_id,
            crop_type=d.crop_type,
            quantity_needed_kg=d.quantity_needed_kg,
            price_offer_per_kg=new_price_offer_per_kg if d.id == demand_id else d.price_offer_per_kg,
            accepted_quality_grades=d.accepted_quality_grades,
        )
        for d in demands
    ]
    return solve_matches(listings, updated)

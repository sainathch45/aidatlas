"""Feature 2: a grounded, auditable negotiation assistant (Part C of the
"make it exciting" revision, judge-eval 2026-10-16).

Pure orchestration -- no Firestore calls here; main.py persists the
transcript afterward. Every proposed price comes from
solver.negotiation_concession_schedule (deterministic, solver-owned) and
is re-validated against the live marketplace via solver.apply_negotiation
BEFORE either side's narration is generated. Gemini only narrates a
number already decided elsewhere -- the same law as every other function
in this codebase.

Pitch/demo framing (say this, not "AI agents negotiate autonomously"):
"Each side's opening position and how fast it concedes are grounded in
the same real urgency math the solver already uses -- and every proposed
price is checked against the live marketplace before either side sees
it. Nothing is agreed without a human's final tap."
"""
from __future__ import annotations

from google import genai

from extraction import narrate_negotiation_turn
from solver import Demand, Listing, apply_negotiation, negotiation_concession_schedule


def run_negotiation(
    client: genai.Client,
    listings: list[Listing],
    demands: list[Demand],
    listing_id: str,
    demand_id: str,
    start_price: float,
    farmer_floor: float,
    buyer_ceiling: float,
    urgency_multiplier: float,
    language: str,
    max_turns: int = 4,
) -> dict:
    """Returns {"turns": [...], "final_price_per_kg": float, "outcome":
    "no_overlap" | "infeasible" | "converged"}. Never mutates any stored
    match -- the human's confirm-price tap is the only thing that does.
    """
    schedule = negotiation_concession_schedule(start_price, farmer_floor, buyer_ceiling, urgency_multiplier, max_turns)
    if not schedule:
        return {"turns": [], "final_price_per_kg": start_price, "outcome": "no_overlap"}

    reason = f"this listing's urgency multiplier is {urgency_multiplier:.2f}x (1.0x = no time pressure, 2.0x = at or past the pickup deadline)"
    context = {"reason": reason}

    turns = []
    last_feasible_price = start_price
    previous_price = start_price
    for proposed_price in schedule:
        results = apply_negotiation(listings, demands, demand_id, proposed_price)
        outcome_for_listing = [r for r in results if r.listing_id == listing_id]
        if not outcome_for_listing:
            # Infeasible at this price -- stop here, fall back to the
            # last price that actually cleared the live marketplace.
            break
        last_feasible_price = outcome_for_listing[0].price_agreed_per_kg

        farmer_message = narrate_negotiation_turn(client, "farmer", proposed_price, context, language)
        buyer_message = narrate_negotiation_turn(client, "buyer", proposed_price, context, language)
        turns.append({
            "proposed_price_per_kg": proposed_price,
            "farmer_message": farmer_message,
            "buyer_message": buyer_message,
        })

        if abs(proposed_price - previous_price) <= 0.01:
            break  # converged within epsilon -- further turns would be noise
        previous_price = proposed_price

    outcome = "converged" if turns else "infeasible"
    return {"turns": turns, "final_price_per_kg": last_feasible_price, "outcome": outcome}

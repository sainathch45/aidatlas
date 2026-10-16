"""Standalone validation of the matching solver before any Gemini/Firestore
wiring (PRD docs/PARALI_SETU_PRD.md, Section 15.1, Phase 1) -- same
"prove it in isolation first" discipline used for AidAtlas's OR-Tools layer.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from solver import (
    Demand,
    Listing,
    apply_negotiation,
    negotiation_concession_schedule,
    score_no_burn_submission,
    solve_matches,
    trust_multiplier,
    urgency_multiplier,
)


def test_basic_match_happens():
    listings = [Listing(id="l1", farmer_id="f1", quantity_kg=500, crop_type="rice_stubble")]
    demands = [Demand(id="d1", company_id="c1", crop_type="rice_stubble",
                       quantity_needed_kg=1000, price_offer_per_kg=8.0)]
    results = solve_matches(listings, demands)
    assert len(results) == 1
    assert results[0].matched_kg == 500
    assert results[0].price_agreed_per_kg == 8.0


def test_crop_type_mismatch_excluded():
    listings = [Listing(id="l1", farmer_id="f1", quantity_kg=500, crop_type="wheat_stubble")]
    demands = [Demand(id="d1", company_id="c1", crop_type="rice_stubble",
                       quantity_needed_kg=1000, price_offer_per_kg=8.0)]
    assert solve_matches(listings, demands) == []


def test_quality_grade_filter():
    listings = [Listing(id="l1", farmer_id="f1", quantity_kg=500, crop_type="rice_stubble", quality_grade="wet")]
    demands = [Demand(id="d1", company_id="c1", crop_type="rice_stubble",
                       quantity_needed_kg=1000, price_offer_per_kg=8.0,
                       accepted_quality_grades=("unknown", "dry"))]
    assert solve_matches(listings, demands) == []


def test_unknown_quality_grade_passes_any_spec():
    listings = [Listing(id="l1", farmer_id="f1", quantity_kg=500, crop_type="rice_stubble", quality_grade="unknown")]
    demands = [Demand(id="d1", company_id="c1", crop_type="rice_stubble",
                       quantity_needed_kg=1000, price_offer_per_kg=8.0,
                       accepted_quality_grades=("unknown", "dry"))]
    results = solve_matches(listings, demands)
    assert len(results) == 1


def test_solver_picks_higher_price_when_two_companies_compete():
    listings = [Listing(id="l1", farmer_id="f1", quantity_kg=500, crop_type="rice_stubble")]
    demands = [
        Demand(id="d_low", company_id="c_low", crop_type="rice_stubble",
               quantity_needed_kg=500, price_offer_per_kg=7.0),
        Demand(id="d_high", company_id="c_high", crop_type="rice_stubble",
               quantity_needed_kg=500, price_offer_per_kg=9.0),
    ]
    results = solve_matches(listings, demands)
    assert len(results) == 1
    assert results[0].demand_id == "d_high"
    assert results[0].matched_kg == 500


def test_demand_capacity_caps_total_matched():
    listings = [
        Listing(id="l1", farmer_id="f1", quantity_kg=600, crop_type="rice_stubble"),
        Listing(id="l2", farmer_id="f2", quantity_kg=600, crop_type="rice_stubble"),
    ]
    demands = [Demand(id="d1", company_id="c1", crop_type="rice_stubble",
                       quantity_needed_kg=800, price_offer_per_kg=8.0)]
    results = solve_matches(listings, demands)
    assert sum(r.matched_kg for r in results) == 800


def test_listing_quantity_caps_total_matched_across_demands():
    listings = [Listing(id="l1", farmer_id="f1", quantity_kg=500, crop_type="rice_stubble")]
    demands = [
        Demand(id="d1", company_id="c1", crop_type="rice_stubble",
               quantity_needed_kg=300, price_offer_per_kg=8.0),
        Demand(id="d2", company_id="c2", crop_type="rice_stubble",
               quantity_needed_kg=300, price_offer_per_kg=8.0),
    ]
    results = solve_matches(listings, demands)
    assert sum(r.matched_kg for r in results) == 500


def test_no_demand_returns_empty_not_error():
    listings = [Listing(id="l1", farmer_id="f1", quantity_kg=500, crop_type="rice_stubble")]
    assert solve_matches(listings, []) == []


def test_apply_negotiation_updates_price_and_can_change_outcome():
    listings = [Listing(id="l1", farmer_id="f1", quantity_kg=500, crop_type="rice_stubble")]
    demands = [
        Demand(id="d_low", company_id="c_low", crop_type="rice_stubble",
               quantity_needed_kg=500, price_offer_per_kg=7.0),
        Demand(id="d_high", company_id="c_high", crop_type="rice_stubble",
               quantity_needed_kg=500, price_offer_per_kg=9.0),
    ]
    baseline = solve_matches(listings, demands)
    assert baseline[0].demand_id == "d_high"

    # Farmer negotiates d_low up past d_high's offer -- outcome should flip.
    renegotiated = apply_negotiation(listings, demands, demand_id="d_low", new_price_offer_per_kg=9.5)
    assert renegotiated[0].demand_id == "d_low"
    assert renegotiated[0].price_agreed_per_kg == 9.5


def test_seed_data_generators_produce_demo_scale_sets():
    from seed_data import generate_demo_demand, generate_demo_listings, generate_forecast_corpus

    listings = generate_demo_listings()
    demands = generate_demo_demand()
    corpus = generate_forecast_corpus()

    assert 15 <= len(listings) <= 20
    assert len(demands) == 5
    # 5 companies x 104 weeks, per PRD Section 11's forecast training corpus.
    assert len(corpus) == 5 * 104


def test_urgency_weighting_prefers_urgent_listing_even_into_the_cheaper_demand():
    """Feature 1: an urgent listing (ready_by today) should win preferential
    placement over a calm one (no ready_by) even into a lower-priced demand,
    with the calm listing picking up only whatever capacity is left over --
    not the naive "best price wins" allocation that ignores urgency.
    """
    today = date(2026, 10, 16)
    listings = [
        Listing(id="l_urgent", farmer_id="f_urgent", quantity_kg=300,
                crop_type="rice_stubble", ready_by=today.isoformat()),
        Listing(id="l_calm", farmer_id="f_calm", quantity_kg=400,
                crop_type="rice_stubble", ready_by=None),
    ]
    demands = [
        Demand(id="d_cheap", company_id="c1", crop_type="rice_stubble",
               quantity_needed_kg=200, price_offer_per_kg=5.0),
        Demand(id="d_expensive", company_id="c2", crop_type="rice_stubble",
               quantity_needed_kg=200, price_offer_per_kg=6.0),
    ]
    results = solve_matches(listings, demands, today=today)

    urgent_matched = sum(r.matched_kg for r in results if r.listing_id == "l_urgent")
    calm_matched = sum(r.matched_kg for r in results if r.listing_id == "l_calm")
    assert urgent_matched == 300, "the urgent listing should be fully matched"
    assert calm_matched == 100, "the calm listing should only pick up the leftover demand"
    assert any(r.listing_id == "l_urgent" and r.demand_id == "d_cheap" for r in results), (
        "the urgent listing should win placement into the cheaper demand too, not just the pricier one"
    )
    for r in results:
        expected = urgency_multiplier(
            listings[0].ready_by if r.listing_id == "l_urgent" else listings[1].ready_by, today
        )
        assert r.urgency_multiplier_applied == expected


def test_trust_multiplier_neutral_at_default_and_capped_at_extremes():
    assert trust_multiplier(None) == 1.0, "missing score should be neutral, same discipline as missing ready_by"
    assert trust_multiplier(0.5) == 1.0
    assert trust_multiplier(1.0) == 1.15
    assert trust_multiplier(0.0) == 0.85


def test_score_no_burn_submission_combination_table():
    # Both sources agree, both positive.
    result = score_no_burn_submission(0.5, "unburned", "no_fire_detected")
    assert result == {"new_score": 0.65, "disputed": False}

    # Photo claims unburned but satellite independently detected a real
    # fire -- disputed, and the false claim does NOT get full credit.
    result = score_no_burn_submission(0.5, "unburned", "fire_detected")
    assert result["disputed"] is True
    assert result["new_score"] == 0.45  # +0.10 (photo) - 0.15 (satellite), netted but flagged

    # No satellite data available -- only the photo delta applies.
    result = score_no_burn_submission(0.5, "burned", "no_data")
    assert result == {"new_score": 0.30, "disputed": False}

    # Missing previous score defaults to the neutral 0.5.
    result = score_no_burn_submission(None, "partially_burned", "no_fire_detected")
    assert result["new_score"] == round(0.5 - 0.05 + 0.05, 3)

    # Clamp bounds: can't go below 0 or above 1.
    assert score_no_burn_submission(0.1, "burned", "fire_detected")["new_score"] == 0.0
    assert score_no_burn_submission(0.95, "unburned", "no_fire_detected")["new_score"] == 1.0


def test_trust_multiplier_biases_the_objective_like_urgency_does():
    """A high-trust listing should win placement into a demand over an
    equally-priced, equally-urgent but lower-trust listing competing for
    the same limited capacity -- same decay-aware-style tiebreak as
    urgency, just a smaller (+-15%) lever.
    """
    listings = [
        Listing(id="l_trusted", farmer_id="f_trusted", quantity_kg=100,
                crop_type="rice_stubble", trust_score=1.0),
        Listing(id="l_untrusted", farmer_id="f_untrusted", quantity_kg=100,
                crop_type="rice_stubble", trust_score=0.0),
    ]
    demands = [Demand(id="d1", company_id="c1", crop_type="rice_stubble",
                       quantity_needed_kg=100, price_offer_per_kg=8.0)]
    results = solve_matches(listings, demands)
    assert len(results) == 1
    assert results[0].listing_id == "l_trusted", "the higher-trust listing should win the limited demand slot"


def test_custom_constraint_shifts_allocation_toward_the_target():
    """Part D: with ample supply of both grades and the demand's capacity
    as the binding limit (so price alone gives no preference), a stated
    quality_ratio_min constraint should pull the allocation up to its
    target -- not just sit there unused.
    """
    listings = [
        Listing(id="l_dry", farmer_id="f1", quantity_kg=80, crop_type="rice_stubble", quality_grade="dry"),
        Listing(id="l_wet", farmer_id="f2", quantity_kg=80, crop_type="rice_stubble", quality_grade="wet"),
    ]
    demands = [Demand(id="d1", company_id="c1", crop_type="rice_stubble",
                       quantity_needed_kg=100, price_offer_per_kg=8.0,
                       accepted_quality_grades=("dry", "wet"))]
    results = solve_matches(
        listings, demands,
        custom_constraints={"d1": [{"constraint_type": "quality_ratio_min", "quality_grade": "dry", "threshold": 0.6}]},
    )
    by_listing = {r.listing_id: r.matched_kg for r in results}
    assert by_listing.get("l_dry", 0) >= 60.0, f"expected at least 60kg dry to hit the 60% target: {by_listing}"


def test_custom_constraint_degrades_gracefully_when_unsatisfiable():
    """Part D regression test: a target grade with zero available supply
    must still produce a matched result (a reported shortfall), never an
    empty/infeasible list -- a real bug found live where an earlier
    (reverted) formulation anchored to realized total flow instead of
    the demand's fixed quantity_needed_kg, making the deterrent penalty
    also block the basic "match at all" decision whenever the target was
    unreachable.
    """
    listings = [Listing(id="l_wet", farmer_id="f1", quantity_kg=100, crop_type="rice_stubble", quality_grade="wet")]
    demands = [Demand(id="d1", company_id="c1", crop_type="rice_stubble",
                       quantity_needed_kg=100, price_offer_per_kg=8.0,
                       accepted_quality_grades=("dry", "wet"))]
    results = solve_matches(
        listings, demands,
        custom_constraints={"d1": [{"constraint_type": "quality_ratio_min", "quality_grade": "dry", "threshold": 0.6}]},
    )
    assert results, "must still match the available wet supply even though the dry target is unreachable"
    assert results[0].matched_kg == 100.0


def test_custom_constraint_holds_against_a_higher_paying_alternative():
    """Part D: the deterrent penalty must survive a real competing price
    incentive to abandon the constraint entirely, not just an artificial
    tie-break scenario.
    """
    listings = [Listing(id="l_dry", farmer_id="f1", quantity_kg=100, crop_type="rice_stubble", quality_grade="dry")]
    demands = [
        Demand(id="d1", company_id="c1", crop_type="rice_stubble", quantity_needed_kg=100, price_offer_per_kg=8.0),
        Demand(id="d2", company_id="c2", crop_type="rice_stubble", quantity_needed_kg=100, price_offer_per_kg=20.0),
    ]
    results = solve_matches(
        listings, demands,
        custom_constraints={"d1": [{"constraint_type": "quality_ratio_min", "quality_grade": "dry", "threshold": 0.6}]},
    )
    by_demand = {r.demand_id: r.matched_kg for r in results}
    assert by_demand.get("d1", 0) >= 60.0, f"the constraint should hold even against a 2.5x price incentive: {by_demand}"


def test_negotiation_schedule_empty_when_no_overlap():
    assert negotiation_concession_schedule(8.0, farmer_floor=11.0, buyer_ceiling=10.0, urgency_multiplier=2.0) == []


def test_negotiation_schedule_never_exceeds_max_turns():
    schedule = negotiation_concession_schedule(8.0, farmer_floor=7.0, buyer_ceiling=10.0, urgency_multiplier=2.0, max_turns=4)
    assert len(schedule) <= 4


def test_negotiation_schedule_high_urgency_concedes_faster():
    low = negotiation_concession_schedule(8.0, farmer_floor=7.0, buyer_ceiling=10.0, urgency_multiplier=1.0, max_turns=4)
    high = negotiation_concession_schedule(8.0, farmer_floor=7.0, buyer_ceiling=10.0, urgency_multiplier=2.0, max_turns=4)
    for lo_price, hi_price in zip(low, high):
        assert hi_price < lo_price, (
            f"a higher-urgency listing should concede closer to the standing offer at every turn: {low} vs {high}"
        )


def test_seed_demo_set_is_solvable_end_to_end():
    from seed_data import generate_demo_demand, generate_demo_listings

    results = solve_matches(generate_demo_listings(), generate_demo_demand())
    assert len(results) > 0
    for r in results:
        assert r.matched_kg > 0
        assert r.price_agreed_per_kg > 0

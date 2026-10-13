"""Standalone validation of the matching solver before any Gemini/Firestore
wiring (PRD docs/PARALI_SETU_PRD.md, Section 15.1, Phase 1) -- same
"prove it in isolation first" discipline used for AidAtlas's OR-Tools layer.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from solver import Demand, Listing, apply_negotiation, solve_matches


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


def test_seed_demo_set_is_solvable_end_to_end():
    from seed_data import generate_demo_demand, generate_demo_listings

    results = solve_matches(generate_demo_listings(), generate_demo_demand())
    assert len(results) > 0
    for r in results:
        assert r.matched_kg > 0
        assert r.price_agreed_per_kg > 0

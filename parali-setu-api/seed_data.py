"""Synthetic seed data for Parali Setu (PRD docs/PARALI_SETU_PRD.md, Section 11).

Two distinct datasets, generated separately on purpose:

1. The small *live-demo* set (~15-20 listings, 5 companies) -- what the
   solver matches live, on camera, during the recorded demo.
2. The *forecast training corpus* (~104 weekly points per product/region
   series, ~2 synthetic years) -- what BigQuery ML's seasonal forecast
   trains on. Deliberately separate and much larger than (1), so the
   forecast isn't fit on a handful of rows (this was a specific gap an
   earlier PRD revision was scored down for leaving ambiguous).

Both are synthetic and labelled as such everywhere they're used -- see
PRD Section 11 for the real reference data (district residue baselines,
Agmarknet, festival calendar) these are shaped against.
"""
from __future__ import annotations

import csv
import json
import math
import random
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

from solver import Demand, Listing

PUNJAB_HARYANA_DISTRICTS = [
    "Sangrur", "Patiala", "Bathinda", "Ludhiana", "Moga",
    "Karnal", "Kaithal", "Kurukshetra",
]

CROP_TYPES = ["rice_stubble", "wheat_stubble"]

PRODUCT_LINES = ["disposable_plates", "biofuel_pellets", "packaging_board", "road_composite"]

# Companies and the regions they ship finished product to, for the
# festival-seasonality corpus below -- not real company names, just
# representative of the categories in PRD Section 7.1.
COMPANY_SEEDS = [
    {"id": "co_1", "name": "Co_Plates_Gujarat", "product": "disposable_plates", "region": "Gujarat"},
    {"id": "co_2", "name": "Co_Pellets_Punjab", "product": "biofuel_pellets", "region": "Punjab"},
    {"id": "co_3", "name": "Co_Board_WestBengal", "product": "packaging_board", "region": "West Bengal"},
    {"id": "co_4", "name": "Co_Road_Haryana", "product": "road_composite", "region": "Haryana"},
    {"id": "co_5", "name": "Co_Plates_Delhi", "product": "disposable_plates", "region": "Delhi"},
]

# Rough festival weeks (ISO week number) where demand for disposable
# plates/packaging genuinely spikes in India -- Navratri/Diwali window
# falls in Sept-Nov, shifting slightly year to year with the lunar
# calendar. This is a pattern-based approximation, not an ephemeris.
FESTIVAL_PEAK_WEEKS = [39, 40, 41, 44, 45]


def generate_demo_listings(seed: int = 42, count: int = 18) -> list[Listing]:
    """~15-20 farmer listings for the live demo (PRD Section 15)."""
    rng = random.Random(seed)
    listings = []
    for i in range(count):
        listings.append(
            Listing(
                id=f"listing_{i+1}",
                farmer_id=f"farmer_{i+1}",
                quantity_kg=rng.choice([400, 600, 800, 1000, 1200, 1500]),
                crop_type=rng.choice(CROP_TYPES),
                quality_grade=rng.choice(["unknown", "unknown", "dry", "wet", "mixed"]),
            )
        )
    return listings


def generate_demo_demand(seed: int = 42) -> list[Demand]:
    """Standing demand for the 5 demo companies (PRD Section 15)."""
    rng = random.Random(seed)
    demands = []
    for i, co in enumerate(COMPANY_SEEDS):
        demands.append(
            Demand(
                id=f"demand_{i+1}",
                company_id=co["id"],
                crop_type=rng.choice(CROP_TYPES),
                quantity_needed_kg=rng.choice([3000, 4000, 5000, 6000]),
                price_offer_per_kg=round(rng.uniform(7.5, 9.5), 2),
                accepted_quality_grades=("unknown", "dry") if co["product"] == "disposable_plates"
                else ("unknown", "dry", "wet", "mixed"),
            )
        )
    return demands


def generate_forecast_corpus(seed: int = 7, weeks: int = 104) -> list[dict]:
    """~2 synthetic years of weekly demand per product/region series (Section 11).

    Pattern-based: a flat baseline plus a festival bump in the Navratri/
    Diwali weeks and mild noise. This proves the forecasting pipeline and
    gives a directionally plausible example -- it is not a claim of
    real-world forecast accuracy (PRD Section 13.1).
    """
    rng = random.Random(seed)
    start = date(2024, 1, 1)
    rows = []
    for co in COMPANY_SEEDS:
        baseline = rng.uniform(2000, 4000)
        for week_offset in range(weeks):
            d = start + timedelta(weeks=week_offset)
            iso_week = d.isocalendar()[1]
            festival_multiplier = 1.8 if iso_week in FESTIVAL_PEAK_WEEKS else 1.0
            seasonal_wave = 1 + 0.1 * math.sin(2 * math.pi * week_offset / 52)
            noise = rng.uniform(0.92, 1.08)
            demand_units = round(baseline * festival_multiplier * seasonal_wave * noise, 1)
            rows.append(
                {
                    "company_id": co["id"],
                    "product": co["product"],
                    "region": co["region"],
                    "week_start": d.isoformat(),
                    "demand_units": demand_units,
                }
            )
    return rows


def write_seed_files(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    listings = [asdict(l) for l in generate_demo_listings()]
    demands = [asdict(d) for d in generate_demo_demand()]
    corpus = generate_forecast_corpus()

    (out_dir / "demo_listings.json").write_text(json.dumps(listings, indent=2))
    (out_dir / "demo_demand.json").write_text(json.dumps(demands, indent=2))

    with (out_dir / "forecast_training_corpus.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["company_id", "product", "region", "week_start", "demand_units"])
        writer.writeheader()
        writer.writerows(corpus)


if __name__ == "__main__":
    write_seed_files(Path(__file__).parent / "seed")
    print("Wrote demo_listings.json, demo_demand.json, forecast_training_corpus.csv to ./seed/")

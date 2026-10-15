"""Firestore read/write helpers for Parali Setu's data model (PRD
docs/PARALI_SETU_PRD.md, Section 10). Thin wrappers only -- no business
logic here, that's solver.py (numbers) and extraction.py (language).

Shares the ai-builder-cup-aidatlas GCP project with AidAtlas but uses
disjoint collection names (listings/companies/demand/matches/forecasts
vs. AidAtlas's single "allocations" collection) -- confirmed no overlap
before reusing the project.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from google.cloud import firestore

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "ai-builder-cup-aidatlas")


def get_firestore_client() -> firestore.Client:
    return firestore.Client(project=PROJECT_ID)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def save_listing(db: firestore.Client, farmer_id: str, extracted: dict, language: str) -> dict:
    listing = {
        "id": _new_id("listing"),
        "farmer_id": farmer_id,
        "quantity_kg": extracted.get("quantity_kg"),
        "crop_type": extracted.get("crop_type"),
        "village_or_district": extracted.get("village_or_district"),
        "ready_by": extracted.get("ready_by"),
        "contact": extracted.get("contact"),
        "quality_grade": extracted.get("quality_grade", "unknown"),
        "status": "open",
        "language": language,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    db.collection("listings").document(listing["id"]).set(listing)
    return listing


def get_open_listings(db: firestore.Client) -> list[dict]:
    docs = db.collection("listings").where("status", "==", "open").stream()
    return [d.to_dict() for d in docs]


def save_company(db: firestore.Client, company: dict) -> dict:
    company = {**company, "id": company.get("id") or _new_id("company")}
    db.collection("companies").document(company["id"]).set(company)
    return company


def save_demand(db: firestore.Client, company_id: str, demand: dict) -> dict:
    demand = {
        **demand,
        "id": demand.get("id") or _new_id("demand"),
        "company_id": company_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    db.collection("demand").document(demand["id"]).set(demand)
    return demand


def get_open_demand(db: firestore.Client) -> list[dict]:
    docs = db.collection("demand").stream()
    return [d.to_dict() for d in docs]


def get_demand_for_company(db: firestore.Client, company_id: str) -> list[dict]:
    docs = db.collection("demand").where("company_id", "==", company_id).stream()
    return [d.to_dict() for d in docs]


def save_matches(db: firestore.Client, match_results: list) -> list[dict]:
    """Overwrites nothing -- each solver run creates fresh match docs.
    Deterministic doc ids aren't used here (unlike AidAtlas's allocations)
    because a listing can legitimately re-match differently after a
    negotiation; callers that want "latest match for this listing" should
    filter by listing_id and sort by created_at.
    """
    saved = []
    batch = db.batch()
    for r in match_results:
        match_doc = {
            "id": _new_id("match"),
            "listing_id": r.listing_id,
            "demand_id": r.demand_id,
            "farmer_id": r.farmer_id,
            "company_id": r.company_id,
            "matched_kg": r.matched_kg,
            "price_agreed_per_kg": r.price_agreed_per_kg,
            "status": "proposed",
            "negotiation_log": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        batch.set(db.collection("matches").document(match_doc["id"]), match_doc)
        saved.append(match_doc)
    if saved:
        batch.commit()
    return saved


def get_matches_for_company(db: firestore.Client, company_id: str) -> list[dict]:
    docs = db.collection("matches").where("company_id", "==", company_id).stream()
    return [d.to_dict() for d in docs]


def get_match(db: firestore.Client, match_id: str) -> dict | None:
    doc = db.collection("matches").document(match_id).get()
    return doc.to_dict() if doc.exists else None


def update_match_status(db: firestore.Client, match_id: str, status: str) -> None:
    db.collection("matches").document(match_id).update({"status": status})


def append_negotiation_log(db: firestore.Client, match_id: str, entry: dict) -> None:
    entry = {**entry, "timestamp": datetime.now(timezone.utc).isoformat()}
    db.collection("matches").document(match_id).update(
        {"negotiation_log": firestore.ArrayUnion([entry])}
    )


def update_match_price(db: firestore.Client, match_id: str, new_price_per_kg: float) -> None:
    db.collection("matches").document(match_id).update({"price_agreed_per_kg": new_price_per_kg})


def get_forecast_for_company(db: firestore.Client, company_id: str) -> dict | None:
    """Reads whatever forecast_pipeline.py last wrote (PRD 12/13.1) --
    never computed here, never live. None if the pipeline hasn't run for
    this company yet; callers must show 'not yet available', not a
    fabricated recommendation (PRD 8.2.2)."""
    doc = db.collection("forecasts").document(f"forecast_{company_id}").get()
    return doc.to_dict() if doc.exists else None

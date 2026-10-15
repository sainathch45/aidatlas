"""Parali Setu backend -- FastAPI app wiring the three layers together
(PRD docs/PARALI_SETU_PRD.md, Section 9):

  Gemini (extraction.py)  ->  language in/out, never a number
  OR-Tools (solver.py)    ->  every price/quantity decision
  Firestore (firestore_store.py) -> the only state, read live by both apps

Voice (Speech-to-Text/Text-to-Speech) and the optional multimodal photo
quality read are both live on /listings/voice. The plain /listings
(JSON) endpoint is the lighter-weight text-only path and doesn't accept
a photo -- bundling it there was a deliberate scope call, not an
oversight, since the photo read is explicitly optional (Section 8.1.3).
"""
from __future__ import annotations

import base64

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import firestore_store as store
from extraction import explain_match, extract_listing, parse_negotiation_price, read_stubble_quality
from gemini_client import get_gemini_client
from solver import Demand, Listing, apply_negotiation, solve_matches
from speech import synthesize_speech, transcribe_audio

app = FastAPI(title="Parali Setu API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ListingRequest(BaseModel):
    farmer_id: str
    raw_text: str
    language: str = "Hindi"


class DemandRequest(BaseModel):
    product: str
    crop_type: str
    quantity_needed_kg: float
    price_offer_per_kg: float
    accepted_quality_grades: list[str] = ["unknown", "dry", "wet", "mixed"]


class NegotiateRequest(BaseModel):
    match_id: str
    raw_text: str


def _to_solver_listing(doc: dict) -> Listing | None:
    if not doc.get("quantity_kg") or not doc.get("crop_type"):
        return None
    return Listing(
        id=doc["id"], farmer_id=doc["farmer_id"],
        quantity_kg=doc["quantity_kg"], crop_type=doc["crop_type"],
        quality_grade=doc.get("quality_grade", "unknown"),
    )


def _to_solver_demand(doc: dict) -> Demand:
    return Demand(
        id=doc["id"], company_id=doc["company_id"], crop_type=doc["crop_type"],
        quantity_needed_kg=doc["quantity_needed_kg"], price_offer_per_kg=doc["price_offer_per_kg"],
        accepted_quality_grades=tuple(doc.get("accepted_quality_grades", ["unknown", "dry", "wet", "mixed"])),
    )


@app.get("/health")
def health():
    return {"status": "ok"}


def _create_listing_from_text(farmer_id: str, raw_text: str, language: str, quality_grade: str = "unknown") -> dict:
    """PRD 8.1 steps 2-6: extract -> write -> solve live -> explain.
    Shared by the text endpoint and the voice endpoint below -- voice
    only adds a transcription step in front of this, never a second
    implementation of it (PRD 8.1: 'Gemini extracts... whether spoken
    or typed' is one path, not two).

    `quality_grade` comes from the optional photo read (PRD 8.1.3),
    determined by the caller before this runs -- this function never
    calls Gemini's vision path itself, it only records whatever grade
    (or "unknown") it's handed.
    """
    db = store.get_firestore_client()
    client = get_gemini_client()

    extracted = extract_listing(client, raw_text, language)
    if extracted is None:
        raise HTTPException(status_code=503, detail="Could not understand the listing right now -- please try again")
    if extracted.get("quantity_kg") is None or extracted.get("crop_type") is None:
        raise HTTPException(status_code=422, detail="Missing quantity or crop type -- please confirm these details")
    extracted["quality_grade"] = quality_grade

    listing_doc = store.save_listing(db, farmer_id, extracted, language)

    all_listings = [l for l in (_to_solver_listing(d) for d in store.get_open_listings(db)) if l]
    all_demand = [_to_solver_demand(d) for d in store.get_open_demand(db)]
    results = solve_matches(all_listings, all_demand)

    this_listing_results = [r for r in results if r.listing_id == listing_doc["id"]]
    saved_matches = store.save_matches(db, this_listing_results)

    explanation = None
    explanation_audio_base64 = None
    if saved_matches:
        m = saved_matches[0]
        company_doc = db.collection("companies").document(m["company_id"]).get()
        company_name = company_doc.to_dict()["name"] if company_doc.exists else m["company_id"]
        explanation = explain_match(
            client,
            {
                "company_name": company_name,
                "matched_kg": m["matched_kg"],
                "price_agreed_per_kg": m["price_agreed_per_kg"],
                "pickup_window": listing_doc.get("ready_by", "to be confirmed"),
            },
            language,
        )
        if explanation:
            audio_bytes = synthesize_speech(explanation, language)
            if audio_bytes:
                explanation_audio_base64 = base64.b64encode(audio_bytes).decode("ascii")

    return {
        "listing": listing_doc,
        "matches": saved_matches,
        "explanation": explanation,
        "explanation_audio_base64": explanation_audio_base64,
    }


@app.post("/listings")
def create_listing(req: ListingRequest):
    return _create_listing_from_text(req.farmer_id, req.raw_text, req.language)


@app.post("/listings/voice")
async def create_listing_voice(
    farmer_id: str,
    language: str,
    audio: UploadFile = File(...),
    photo: UploadFile | None = File(None),
):
    """PRD 8.1.1-3: spoken listing in, 16kHz LINEAR16 mono (matching the
    sample rate confirmed live for both hi-IN and pa-IN -- speech.py),
    plus an optional stubble-pile photo (8.1.3). A failed or skipped
    photo read falls back to quality_grade="unknown", never a guess --
    this mirrors the solver's own "unknown passes any quality_spec"
    eligibility rule (solver.py), so skipping the photo never excludes
    a farmer from matching, it just means quality isn't a filter yet.
    """
    audio_bytes = await audio.read()
    transcript = transcribe_audio(audio_bytes, language)
    if transcript is None:
        raise HTTPException(
            status_code=422,
            detail="Could not transcribe that -- please try again or type the listing instead",
        )

    quality_grade = "unknown"
    quality_note = None
    if photo is not None:
        photo_bytes = await photo.read()
        client = get_gemini_client()
        quality_result = read_stubble_quality(client, photo_bytes, mime_type=photo.content_type or "image/jpeg")
        if quality_result and quality_result.get("quality_grade"):
            quality_grade = quality_result["quality_grade"]
            quality_note = quality_result.get("note")

    result = _create_listing_from_text(farmer_id, transcript, language, quality_grade=quality_grade)
    result["transcript"] = transcript
    result["quality_note"] = quality_note
    return result


@app.post("/companies/{company_id}/demand")
def create_demand(company_id: str, req: DemandRequest):
    db = store.get_firestore_client()
    demand_doc = store.save_demand(db, company_id, req.model_dump())
    return demand_doc


@app.get("/companies/{company_id}/dashboard")
def company_dashboard(company_id: str):
    """PRD 8.2.2: Incoming Supply, Active Matches, and the Recommendation
    panel -- read from whatever forecast_pipeline.py last wrote to
    Firestore, never computed here. A company with no forecast doc yet
    gets an explicit 'not yet available', never a fabricated card."""
    db = store.get_firestore_client()
    matches = store.get_matches_for_company(db, company_id)
    forecast = store.get_forecast_for_company(db, company_id)
    return {
        "incoming_supply": sorted(matches, key=lambda m: m.get("price_agreed_per_kg", 0), reverse=True),
        "active_matches": matches,
        "recommendation": forecast,
    }


@app.post("/negotiate")
def negotiate(req: NegotiateRequest):
    """PRD 8.1.7 / 8.2.3: parse the counter-offer, re-solve, log it."""
    db = store.get_firestore_client()
    client = get_gemini_client()

    match = store.get_match(db, req.match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")

    parsed = parse_negotiation_price(client, req.raw_text, match["price_agreed_per_kg"])
    if parsed is None:
        raise HTTPException(status_code=503, detail="Could not understand the request right now -- please try again")
    if not parsed.get("is_price_request") or parsed.get("requested_price_per_kg") is None:
        return {"match": match, "explanation": "No specific price change was understood from that message."}

    all_listings = [l for l in (_to_solver_listing(d) for d in store.get_open_listings(db)) if l]
    all_demand = [_to_solver_demand(d) for d in store.get_open_demand(db)]
    new_results = apply_negotiation(all_listings, all_demand, match["demand_id"], parsed["requested_price_per_kg"])

    store.append_negotiation_log(db, req.match_id, {
        "request_text": req.raw_text,
        "structured_delta": parsed,
    })

    outcome_for_listing = [r for r in new_results if r.listing_id == match["listing_id"]]
    if outcome_for_listing:
        store.update_match_price(db, req.match_id, outcome_for_listing[0].price_agreed_per_kg)
        return {"outcome": "updated", "new_price_per_kg": outcome_for_listing[0].price_agreed_per_kg}
    return {"outcome": "not_feasible", "reason": "No company can take this listing at the requested price"}

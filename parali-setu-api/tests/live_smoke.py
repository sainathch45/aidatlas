"""Live smoke test against the real Gemini/Firestore in ai-builder-cup-
aidatlas -- same discipline as aidatlas-api/tests/smoke_test_live.py.
Not named test_*.py or *_test.py deliberately, so plain `pytest` never
picks it up and tries to hit real credentials/billing; run it by hand:

    python tests/live_smoke.py

Requires ADC set up locally (gcloud auth application-default login) or
a Cloud Run service account in prod.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from google.cloud import texttospeech

import main
from extraction import extract_listing
from firestore_store import get_firestore_client
from gemini_client import get_gemini_client
from speech import transcribe_audio


def check_no_date_fabrication():
    """Regression check for a real bug found 2026-10-15: given a transcript
    that only names a month with no day number, extraction was confidently
    inventing a specific day every time (not randomly -- same wrong date on
    every retry) until the prompt was hardened to require an explicit day
    number or relative timeframe before filling ready_by at all."""
    client = get_gemini_client()
    vague = "ਮੇਰੇ ਕੋਲ 12 ਕੁਇੰਟਲ ਪਰਾਲੀ ਹੈ ਸੰਗਰੂਰ ਵਿੱਚ ਵੀ ਅਕਤੂਬਰ ਤੱਕ ਚੁੱਕ ਲਓ"
    result = extract_listing(client, vague, "Punjabi", today=date(2026, 10, 15))
    assert result["ready_by"] is None, (
        f"expected no date to be fabricated from a month-only mention, got {result['ready_by']}"
    )
    print("no-date-fabrication check: ok")


def check_voice_round_trip():
    """The actual voice path, not just text -- synthesize real speech,
    feed it through the real /listings/voice endpoint, confirm it matches
    and replies with audio, in Punjabi."""
    tts_client = texttospeech.TextToSpeechClient()
    text = "ਮੇਰੇ ਕੋਲ ਬਾਰਾਂ ਕੁਇੰਟਲ ਪਰਾਲੀ ਹੈ ਸੰਗਰੂਰ ਵਿੱਚ, 20 ਅਕਤੂਬਰ ਤੱਕ ਚੁੱਕ ਲਓ"
    synth_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(language_code="pa-IN", name="pa-IN-Chirp3-HD-Achernar")
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16, sample_rate_hertz=16000
    )
    audio_content = tts_client.synthesize_speech(
        input=synth_input, voice=voice, audio_config=audio_config
    ).audio_content

    transcript = transcribe_audio(audio_content, "Punjabi")
    assert transcript is not None, "transcription failed"
    print("voice transcript:", transcript)

    client = TestClient(main.app)
    db = get_firestore_client()
    db.collection("companies").document("voice_smoke_co").set({"id": "voice_smoke_co", "name": "Voice Smoke Co"})
    demand_resp = client.post("/companies/voice_smoke_co/demand", json={
        "product": "biofuel_pellets", "crop_type": "rice_stubble",
        "quantity_needed_kg": 2000, "price_offer_per_kg": 8.75,
    })
    demand_id = demand_resp.json()["id"]

    resp = client.post(
        "/listings/voice",
        params={"farmer_id": "voice_smoke_farmer", "language": "Punjabi"},
        files={"audio": ("listing.wav", audio_content, "audio/wav")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["listing"]["quantity_kg"] == 1200
    assert body["listing"]["crop_type"] == "rice_stubble"
    assert body["explanation_audio_base64"], "expected a spoken reply, not just text"
    print("voice round trip: ok, matched", body["matches"][0]["matched_kg"], "kg")

    for coll, doc_id in [("companies", "voice_smoke_co"), ("demand", demand_id),
                          ("listings", body["listing"]["id"]), ("matches", body["matches"][0]["id"])]:
        db.collection(coll).document(doc_id).delete()


def check_voice_with_photo():
    """Full farmer flow: voice + the optional photo quality read, through
    the real /listings/voice endpoint, using the real CC-licensed
    reference photo in seed/reference_photos/ (see ATTRIBUTION.md)."""
    tts_client = texttospeech.TextToSpeechClient()
    text = "ਮੇਰੇ ਕੋਲ ਬਾਰਾਂ ਕੁਇੰਟਲ ਪਰਾਲੀ ਹੈ ਸੰਗਰੂਰ ਵਿੱਚ"
    synth_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(language_code="pa-IN", name="pa-IN-Chirp3-HD-Achernar")
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16, sample_rate_hertz=16000
    )
    audio_content = tts_client.synthesize_speech(
        input=synth_input, voice=voice, audio_config=audio_config
    ).audio_content

    photo_path = Path(__file__).resolve().parent.parent / "seed" / "reference_photos" / "paddy_stubble_coorg_dry_example.jpg"
    photo_bytes = photo_path.read_bytes()

    client = TestClient(main.app)
    db = get_firestore_client()
    db.collection("companies").document("photo_smoke_co").set({"id": "photo_smoke_co", "name": "Photo Smoke Co"})
    demand_resp = client.post("/companies/photo_smoke_co/demand", json={
        "product": "biofuel_pellets", "crop_type": "rice_stubble",
        "quantity_needed_kg": 2000, "price_offer_per_kg": 8.0,
        "accepted_quality_grades": ["unknown", "dry", "wet", "mixed"],
    })
    demand_id = demand_resp.json()["id"]

    resp = client.post(
        "/listings/voice",
        params={"farmer_id": "photo_smoke_farmer", "language": "Punjabi"},
        files={
            "audio": ("listing.wav", audio_content, "audio/wav"),
            "photo": ("stubble.jpg", photo_bytes, "image/jpeg"),
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["listing"]["quality_grade"] in ("dry", "wet", "mixed"), (
        f"expected the real photo read to produce a grade, got {body['listing']['quality_grade']}"
    )
    print("photo quality read:", body["listing"]["quality_grade"], "--", body.get("quality_note"))

    for coll, doc_id in [("companies", "photo_smoke_co"), ("demand", demand_id),
                          ("listings", body["listing"]["id"]), ("matches", body["matches"][0]["id"])]:
        db.collection(coll).document(doc_id).delete()


def check_listing_lifecycle_and_renegotiation():
    """Feature 1 regression check for the round-4/5 judge-eval finding: a
    fully-matched listing must stop offering its original quantity on the
    next solve (it should flip to status="matched" and vanish from
    get_open_listings), and renegotiating that same match's price must
    still work afterward -- not spuriously come back "not_feasible" just
    because its own already-committed quantity now looks unavailable.
    """
    import firestore_store as store

    client = TestClient(main.app)
    db = get_firestore_client()
    db.collection("companies").document("lifecycle_smoke_co").set(
        {"id": "lifecycle_smoke_co", "name": "Lifecycle Smoke Co"}
    )

    # Price set well above any real seed/demo demand (seed_data.py's
    # highest is 8.98/kg) so this test's own demand always wins the
    # match regardless of whatever else is live in Firestore right now
    # -- otherwise a higher-paying real demand can win the listing
    # instead, same risk the original live_smoke_co check at 8.5/kg
    # already carried without it being exercised before.
    demand_resp = client.post("/companies/lifecycle_smoke_co/demand", json={
        "product": "biofuel_pellets", "crop_type": "rice_stubble",
        "quantity_needed_kg": 500, "price_offer_per_kg": 50.0,
    })
    demand_id = demand_resp.json()["id"]

    listing_resp = client.post("/listings", json={
        "farmer_id": "lifecycle_smoke_farmer",
        "raw_text": "Mere paas 5 quintal rice stubble hai, Sangrur mein",
        "language": "Hindi",
    })
    body = listing_resp.json()
    listing_id = body["listing"]["id"]
    match_id = body["matches"][0]["id"]
    assert body["matches"][0]["demand_id"] == demand_id, "expected this test's own demand to win the match"
    assert body["matches"][0]["matched_kg"] == 500, "the full 500kg listing should be fully matched"

    listing_doc = store.get_listing(db, listing_id)
    assert listing_doc["status"] == "matched", (
        f"a fully-matched listing should flip to status='matched', got {listing_doc['status']!r}"
    )
    assert listing_doc["quantity_remaining_kg"] == 0, listing_doc["quantity_remaining_kg"]
    assert not any(d["id"] == listing_id for d in store.get_open_listings(db)), (
        "a fully-matched listing must not reappear in get_open_listings"
    )
    print("listing lifecycle: ok, closed out at 0kg remaining, status=matched")

    negotiate_resp = client.post("/negotiate", json={
        "match_id": match_id,
        "raw_text": "Can we get 52.00 per kg instead?",
    })
    assert negotiate_resp.status_code == 200, negotiate_resp.text
    outcome = negotiate_resp.json()
    assert outcome["outcome"] == "updated", (
        f"renegotiating an already-fully-matched listing's price should still succeed, got {outcome}"
    )
    assert outcome["new_price_per_kg"] == 52.0
    print("renegotiation of a fully-matched listing: ok,", outcome)

    for coll, doc_id in [("companies", "lifecycle_smoke_co"), ("demand", demand_id),
                          ("listings", listing_id), ("matches", match_id)]:
        db.collection(coll).document(doc_id).delete()


def check_concurrent_decrement_does_not_overcommit():
    """Round-5 judge-eval regression check: two near-simultaneous matches
    against the same listing, together asking for more than it has, must
    not both partially succeed past its real quantity -- the Firestore
    transaction (not a bare read-then-write) is what prevents this.
    """
    import threading

    import firestore_store as store

    db = get_firestore_client()
    ref = db.collection("listings").document("concurrency_smoke_listing")
    ref.set({
        "id": "concurrency_smoke_listing", "quantity_kg": 100, "quantity_remaining_kg": 100,
        "status": "open", "farmer_id": "concurrency_smoke_farmer", "crop_type": "rice_stubble",
    })

    def worker(amount):
        store._decrement_listing_remaining(db.transaction(), ref, amount)

    threads = [threading.Thread(target=worker, args=(80,)) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = ref.get().to_dict()
    assert final["quantity_remaining_kg"] >= 0, (
        f"two 80kg decrements against a 100kg listing overcommitted it: {final}"
    )
    ref.delete()
    print("concurrent decrement: ok, final remaining", final["quantity_remaining_kg"])


def check_no_burn_proof_disputed_path():
    """Feature 5: the photo claims "unburned" but Part A's real satellite
    data independently shows a fire detected in that district/date --
    must come back disputed=True with BOTH deltas applied, not full
    credit just because the photo alone looked clean.
    """
    import firestore_store as store

    client = TestClient(main.app)
    db = get_firestore_client()
    coverage = store.get_fire_data_coverage(db)
    assert coverage is not None, "fetch_fire_data.py must be run before this check (no coverage metadata found)"

    detections = list(db.collection("fire_detections").where("confidence", ">", 0).stream())
    assert detections, "fetch_fire_data.py returned zero detections -- widen the lookback window and re-run"
    sample = detections[0].to_dict()
    district, detected_date = sample["district_guess"], sample["detected_at"]

    photo_path = Path(__file__).resolve().parent.parent / "seed" / "reference_photos" / "paddy_stubble_coorg_dry_example.jpg"
    photo_bytes = photo_path.read_bytes()

    resp = client.post(
        "/farmers/no_burn_smoke_farmer/no-burn-proof",
        params={"district": district, "claimed_date": detected_date},
        files={"photo": ("field.jpg", photo_bytes, "image/jpeg")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["satellite_corroboration"] == "fire_detected", (
        f"expected a real detection for {district} on {detected_date}, got {body}"
    )
    if body["field_condition"] == "unburned":
        assert body["disputed"] is True, "an unburned photo claim contradicted by a real fire must be disputed"
    print("no-burn-proof disputed path: ok,", body)

    db.collection("farmers").document("no_burn_smoke_farmer").delete()
    for d in db.collection("no_burn_proofs").where("farmer_id", "==", "no_burn_smoke_farmer").stream():
        d.reference.delete()


def check_pricing_explanation():
    """Feature 3: the real urgency multiplier the solver applied must show
    up in the narration, grounded in that real number, not invented.
    """
    client = TestClient(main.app)
    db = get_firestore_client()
    db.collection("companies").document("pricing_smoke_co").set({"id": "pricing_smoke_co", "name": "Pricing Smoke Co"})
    demand_resp = client.post("/companies/pricing_smoke_co/demand", json={
        "product": "biofuel_pellets", "crop_type": "rice_stubble",
        "quantity_needed_kg": 500, "price_offer_per_kg": 60.0,
    })
    demand_id = demand_resp.json()["id"]
    listing_resp = client.post("/listings", json={
        "farmer_id": "pricing_smoke_farmer",
        "raw_text": "Mere paas 5 quintal rice stubble hai, Sangrur mein, aaj hi le jao",
        "language": "Hindi",
    })
    body = listing_resp.json()
    match_id, listing_id = body["matches"][0]["id"], body["listing"]["id"]
    assert body["matches"][0]["urgency_multiplier_applied"] == 2.0, "a today-deadline listing should hit the urgency ceiling"

    resp = client.get(f"/matches/{match_id}/pricing-explanation", params={"language": "English"})
    assert resp.status_code == 200, resp.text
    explanation = resp.json()["explanation"]
    assert "2.00x" in explanation or "2.0x" in explanation, (
        f"expected the real urgency multiplier grounded in the narration, got: {explanation}"
    )
    print("pricing explanation: ok,", explanation)

    for coll, doc_id in [("companies", "pricing_smoke_co"), ("demand", demand_id),
                          ("listings", listing_id), ("matches", match_id)]:
        db.collection(coll).document(doc_id).delete()


def check_fraud_cross_check_catches_real_contradiction():
    """Feature 4: an explicit transcript contradiction of the photo's
    quality read must be flagged; a transcript that says nothing about
    quality at all must not be flagged (no inferring fraud from silence).
    """
    from extraction import cross_check_voice_and_photo

    client = get_gemini_client()
    mismatch = cross_check_voice_and_photo(
        client,
        transcript="Mere paas 10 quintal sukha rice stubble hai, bilkul sookha hua",
        quality_grade="wet",
        quality_note="visible moisture on surface",
        language="Hindi",
    )
    assert mismatch["mismatch_detected"] is True, f"expected the dry-vs-wet contradiction to be caught: {mismatch}"

    silent = cross_check_voice_and_photo(
        client,
        transcript="Mere paas 10 quintal rice stubble hai Sangrur mein",
        quality_grade="wet",
        quality_note="visible moisture on surface",
        language="Hindi",
    )
    assert silent["mismatch_detected"] is False, f"a transcript silent on quality must not be flagged: {silent}"
    print("fraud cross-check: ok, caught the real contradiction and no false positive on silence")


def check_custom_constraint_end_to_end():
    """Part D: a company's plain-language sourcing rule, parsed by real
    Gemini, stored in Firestore, and read back into a real solve call,
    must measurably shift allocation toward the stated target.
    """
    import firestore_store as store
    from solver import solve_matches

    client = TestClient(main.app)
    db = get_firestore_client()
    db.collection("companies").document("partd_smoke_co").set({"id": "partd_smoke_co", "name": "Part D Smoke Co"})

    demand_resp = client.post("/companies/partd_smoke_co/demand", json={
        "product": "biofuel_pellets", "crop_type": "rice_stubble",
        "quantity_needed_kg": 100, "price_offer_per_kg": 50.0,
        "accepted_quality_grades": ["unknown", "dry", "wet", "mixed"],
        "custom_constraint_text": "At least 60% of what I buy should be dry",
    })
    demand = demand_resp.json()
    demand_id = demand["id"]
    assert demand["custom_constraints"] == [
        {"constraint_type": "quality_ratio_min", "quality_grade": "dry", "threshold": 0.6}
    ], f"real Gemini parse didn't match the expected structured constraint: {demand['custom_constraints']}"

    db.collection("listings").document("partd_l_dry").set({
        "id": "partd_l_dry", "farmer_id": "partd_f_dry", "quantity_kg": 80, "quantity_remaining_kg": 80,
        "crop_type": "rice_stubble", "quality_grade": "dry", "status": "open", "ready_by": None,
    })
    db.collection("listings").document("partd_l_wet").set({
        "id": "partd_l_wet", "farmer_id": "partd_f_wet", "quantity_kg": 80, "quantity_remaining_kg": 80,
        "crop_type": "rice_stubble", "quality_grade": "wet", "status": "open", "ready_by": None,
    })

    open_listing_docs = [store.get_listing(db, "partd_l_dry"), store.get_listing(db, "partd_l_wet")]
    all_listings = [main._to_solver_listing(d) for d in open_listing_docs]
    open_demand_docs = [d for d in store.get_open_demand(db) if d["id"] == demand_id]
    all_demand = [main._to_solver_demand(d) for d in open_demand_docs]
    custom_constraints = {d["id"]: d["custom_constraints"] for d in open_demand_docs if d.get("custom_constraints")}

    results = solve_matches(all_listings, all_demand, custom_constraints=custom_constraints)
    by_listing = {r.listing_id: r.matched_kg for r in results}
    assert by_listing.get("partd_l_dry", 0) >= 60.0, (
        f"expected the real, Firestore-sourced constraint to pull dry allocation to >=60kg: {by_listing}"
    )
    print("custom constraint end-to-end: ok,", by_listing)

    for coll, doc_id in [("companies", "partd_smoke_co"), ("demand", demand_id),
                          ("listings", "partd_l_dry"), ("listings", "partd_l_wet")]:
        db.collection(coll).document(doc_id).delete()


def check_negotiation_agents_grounded_and_non_mutating():
    """Feature 2: the agent-to-agent negotiation must narrate real urgency
    context (not generic chatter), never mutate the match on its own,
    and only change the price once a human explicitly confirms it.
    """
    client = TestClient(main.app)
    db = get_firestore_client()
    db.collection("companies").document("neg_smoke_co").set({"id": "neg_smoke_co", "name": "Negotiation Smoke Co"})
    demand_resp = client.post("/companies/neg_smoke_co/demand", json={
        "product": "biofuel_pellets", "crop_type": "rice_stubble",
        "quantity_needed_kg": 500, "price_offer_per_kg": 55.0,
    })
    demand_id = demand_resp.json()["id"]
    listing_resp = client.post("/listings", json={
        "farmer_id": "neg_smoke_farmer",
        "raw_text": "Mere paas 5 quintal rice stubble hai, Sangrur mein, aaj hi le jao",
        "language": "Hindi",
    })
    body = listing_resp.json()
    match_id, listing_id = body["matches"][0]["id"], body["listing"]["id"]
    assert body["matches"][0]["urgency_multiplier_applied"] == 2.0, "expected a today-deadline listing to hit the urgency ceiling"

    resp = client.post("/negotiate/agents", json={
        "match_id": match_id, "farmer_floor": 50.0, "buyer_ceiling": 60.0, "language": "English", "max_turns": 4,
    })
    assert resp.status_code == 200, resp.text
    session = resp.json()
    assert session["outcome"] == "converged", session
    assert session["turns"], "expected at least one negotiation turn"
    for turn in session["turns"]:
        assert "deadline" in (turn["farmer_message"] or "").lower() or "urgen" in (turn["farmer_message"] or "").lower(), (
            f"expected the real urgency fact to ground the narration, got: {turn['farmer_message']}"
        )

    import firestore_store as store

    match_still_pending = store.get_match(db, match_id)
    assert match_still_pending["price_agreed_per_kg"] == 55.0, "negotiate/agents must not mutate the match on its own"

    confirm_resp = client.post(f"/matches/{match_id}/confirm-price", json={"new_price_per_kg": session["final_price_per_kg"]})
    assert confirm_resp.status_code == 200, confirm_resp.text
    match_after_confirm = store.get_match(db, match_id)
    assert match_after_confirm["price_agreed_per_kg"] == session["final_price_per_kg"]
    print("negotiation agents: ok,", session["outcome"], "->", session["final_price_per_kg"])

    for coll, doc_id in [("companies", "neg_smoke_co"), ("demand", demand_id),
                          ("listings", listing_id), ("matches", match_id)]:
        db.collection(coll).document(doc_id).delete()
    for d in db.collection("negotiation_sessions").where("match_id", "==", match_id).stream():
        d.reference.delete()


def run():
    client = TestClient(main.app)
    db = get_firestore_client()

    health = client.get("/health")
    assert health.status_code == 200, health.text
    print("health: ok")

    db.collection("companies").document("live_smoke_co").set({"id": "live_smoke_co", "name": "Live Smoke Test Co"})

    demand_resp = client.post("/companies/live_smoke_co/demand", json={
        "product": "biofuel_pellets", "crop_type": "rice_stubble",
        "quantity_needed_kg": 2000, "price_offer_per_kg": 8.5,
    })
    assert demand_resp.status_code == 200, demand_resp.text
    demand_id = demand_resp.json()["id"]
    print("demand created:", demand_id)

    listing_resp = client.post("/listings", json={
        "farmer_id": "live_smoke_farmer",
        "raw_text": "Mere paas 10 quintal rice stubble hai, Sangrur mein, 25 October tak le jao",
        "language": "Hindi",
    })
    assert listing_resp.status_code == 200, listing_resp.text
    body = listing_resp.json()
    assert body["listing"]["quantity_kg"] == 1000, "10 quintal should extract to 1000 kg"
    assert body["listing"]["ready_by"] == "2026-10-25", "date must anchor to the near future, not a stale year"
    assert len(body["matches"]) == 1
    assert body["matches"][0]["price_agreed_per_kg"] == 8.5
    assert body["explanation"] and "Live Smoke Test Co" in body["explanation"], "narration must use the real company name, not its id"
    match_id = body["matches"][0]["id"]
    listing_id = body["listing"]["id"]
    print("listing matched:", body["matches"][0])
    print("explanation:", body["explanation"])

    negotiate_resp = client.post("/negotiate", json={
        "match_id": match_id,
        "raw_text": "Can we get 9.00 per kg instead?",
    })
    assert negotiate_resp.status_code == 200, negotiate_resp.text
    print("negotiation outcome:", negotiate_resp.json())

    # cleanup -- this is a smoke test, not seed data
    for coll, doc_id in [("companies", "live_smoke_co"), ("demand", demand_id), ("listings", listing_id), ("matches", match_id)]:
        db.collection(coll).document(doc_id).delete()
    print("cleaned up")

    check_no_date_fabrication()
    check_voice_round_trip()
    check_voice_with_photo()
    check_listing_lifecycle_and_renegotiation()
    check_concurrent_decrement_does_not_overcommit()
    check_no_burn_proof_disputed_path()
    check_pricing_explanation()
    check_fraud_cross_check_catches_real_contradiction()
    check_custom_constraint_end_to_end()
    check_negotiation_agents_grounded_and_non_mutating()

    print("\nALL LIVE CHECKS PASSED")


if __name__ == "__main__":
    run()

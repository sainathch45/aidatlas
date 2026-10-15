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

    print("\nALL LIVE CHECKS PASSED")


if __name__ == "__main__":
    run()

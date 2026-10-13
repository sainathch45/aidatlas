"""Live smoke test against the real Gemini/Firestore in ai-builder-cup-
aidatlas -- same discipline as aidatlas-api/tests/smoke_test_live.py.
Not named test_*.py or *_test.py deliberately, so plain `pytest` never
picks it up and tries to hit real credentials/billing; run it by hand:

    python tests/live_smoke.py

Requires ADC set up locally (gcloud auth application-default login) or
a Cloud Run service account in prod.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

import main
from firestore_store import get_firestore_client


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
    print("\nALL LIVE CHECKS PASSED")


if __name__ == "__main__":
    run()

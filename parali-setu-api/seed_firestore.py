"""Loads the demo companies and their standing demand (PRD
docs/PARALI_SETU_PRD.md, Section 15) into the real, persistent
Firestore -- separate from tests/live_smoke.py, which creates and
deletes its own throwaway docs. This is what makes the live deployed
site actually matchable: a real farmer submission needs real open
demand to match against.

Deliberately does NOT seed farmer listings too, even though
generate_demo_listings() exists for this purpose -- found live
2026-10-15: an earlier version of this script seeded 18 "open"
listings that silently consumed most of the demand capacity in every
future solve, so a real live demo submission got "no buyer matched
yet" instead of a visible match. Listings aren't shown anywhere in the
UI until they're matched (the dashboard shows matches, not raw
listings), so pre-seeding them bought no visible demo value and cost
real matching capacity -- removed.

Run by hand once after a fresh deploy or a Firestore reset:

    python seed_firestore.py
"""
from __future__ import annotations

from dataclasses import asdict

import firestore_store as store
from seed_data import COMPANY_SEEDS, generate_demo_demand


def run():
    db = store.get_firestore_client()

    for co in COMPANY_SEEDS:
        store.save_company(db, {"id": co["id"], "name": co["name"], "product_lines": [co["product"]]})
    print(f"seeded {len(COMPANY_SEEDS)} companies")

    demands = generate_demo_demand()
    for d in demands:
        db.collection("demand").document(d.id).set(asdict(d))
    print(f"seeded {len(demands)} demand records")

    print("done -- the live dashboard and /listings should now have real standing demand to match against")


if __name__ == "__main__":
    run()

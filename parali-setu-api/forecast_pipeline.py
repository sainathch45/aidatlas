"""Runs the trained BigQuery ML forecast and writes results into Firestore
(PRD docs/PARALI_SETU_PRD.md, Section 10/12) -- an offline batch step, run
once during data seeding, not called live during the demo (Section 13.1).
The company dashboard just reads whatever's in Firestore; it never talks
to BigQuery directly.

Run by hand after bigquery/forecast_model.sql has trained the model:

    python forecast_pipeline.py
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from google.cloud import bigquery

import firestore_store as store

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "ai-builder-cup-aidatlas")

# Demo company ids -> their real Firestore company doc id, set up by
# write_seed_files(). The forecast table keys on the same company_id
# used throughout seed_data.py, so this is just a passthrough map.
QUERY = """
SELECT company_id, product, region, week_start, predicted_demand
FROM `parali_setu.demand_forecast_next_8_weeks`
ORDER BY company_id, week_start
"""


def run():
    bq = bigquery.Client(project=PROJECT_ID)
    db = store.get_firestore_client()

    rows = list(bq.query(QUERY).result())
    print(f"fetched {len(rows)} forecast rows from BigQuery")

    # One forecast doc per company: the dashboard wants a single
    # recommendation card, not 8 weekly rows (PRD 8.2.2) -- pick the
    # highest-demand week in the horizon as "the period to prioritize."
    by_company: dict[str, list] = {}
    for r in rows:
        by_company.setdefault(r.company_id, []).append(r)

    written = 0
    for company_id, weeks in by_company.items():
        peak = max(weeks, key=lambda r: r.predicted_demand)
        forecast_doc = {
            "id": f"forecast_{company_id}",
            "company_id": company_id,
            "product": peak.product,
            "region": peak.region,
            "period": peak.week_start.isoformat(),
            "predicted_demand": round(peak.predicted_demand, 1),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        db.collection("forecasts").document(forecast_doc["id"]).set(forecast_doc)
        written += 1
        print(f"  {company_id}: prioritize {peak.product} in {peak.region}, "
              f"peak week {peak.week_start.date()}, demand {peak.predicted_demand:.0f}")

    print(f"wrote {written} forecast docs to Firestore")


if __name__ == "__main__":
    run()

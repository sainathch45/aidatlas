"""AidAtlas — crisis resource allocator backend.

Deploys to Cloud Run. Calls the free-tier Gemini Developer API directly
(no Agent Platform needed for this), reads district need-scores from
BigQuery (see bigquery/schema.sql), and writes/reads the resulting
allocations + rationale through Firestore for the live dashboard/map.

Local run:
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8080
    (reads GEMINI_API_KEY etc. from .env via python-dotenv)
"""

import json
import os
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from google import genai
from google.cloud import bigquery, firestore
from pydantic import BaseModel

# No-op in Cloud Run (env vars are injected directly there); picks up
# aidatlas-api/.env for local runs.
load_dotenv()

app = FastAPI(title="AidAtlas")

# Confirmed available on the Gemini free tier as of Oct 2026 research; if
# AI Studio's model picker shows a newer default (e.g. a Gemini 3 Flash
# variant) when you get your key, swap this.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
BQ_DATASET = os.environ.get("BIGQUERY_DATASET", "crisis_allocator")

# Real HSYR26 appeal row confirmed in data/raw/hdx-hapi-syr/hdx_hapi_funding_syr.csv.
# Scoped to one region for the MVP, per the plan's "pick one defensible
# crisis" guidance -- multi-region is a go-big extension, not the core.
SYRIA_APPEAL_CODE = "HSYR26"


def get_gemini_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not set")
    return genai.Client(api_key=api_key)


def get_bq_client() -> bigquery.Client:
    return bigquery.Client(project=PROJECT_ID)


def get_firestore_client() -> firestore.Client:
    return firestore.Client(project=PROJECT_ID)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/gemini-ping")
def gemini_ping():
    """Smoke-test the free-tier Gemini key end to end."""
    client = get_gemini_client()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents="Reply with the single word: ready",
    )
    return {"model": GEMINI_MODEL, "reply": response.text}


def fetch_district_need_scores(bq: bigquery.Client) -> list[dict]:
    query = f"""
        SELECT admin1_name, admin2_name, admin2_code, idp_population, active_org_count, need_score
        FROM `{PROJECT_ID}.{BQ_DATASET}.district_need_score`
        WHERE need_score IS NOT NULL
        ORDER BY need_score DESC
    """
    return [dict(row) for row in bq.query(query).result()]


def fetch_supply_pool(bq: bigquery.Client, appeal_code: str) -> float:
    query = f"""
        SELECT funding_usd
        FROM `{PROJECT_ID}.{BQ_DATASET}.raw_funding`
        WHERE appeal_code = @appeal_code
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("appeal_code", "STRING", appeal_code)]
    )
    rows = list(bq.query(query, job_config=job_config).result())
    return float(rows[0]["funding_usd"]) if rows else 0.0


def compute_proportional_allocation(districts: list[dict], supply_pool: float) -> list[dict]:
    """Simple, explainable split: each district gets a share of the real
    funding pool proportional to its need score. Deliberately not a
    fancier optimizer -- the "out-of-the-ordinary twist" here is
    defensible rationale per allocation, not solver sophistication.
    """
    total_need = sum(d["need_score"] for d in districts) or 1
    for d in districts:
        d["quantity_allocated"] = round(supply_pool * d["need_score"] / total_need, 2)
    return districts


def generate_rationale(client: genai.Client, top_districts: list[dict], resource_type: str) -> dict[str, str]:
    """One batched Gemini call for the top allocations, not one call per
    district -- the free tier's ~10-15 req/min would make per-district
    calls impractical, and a coordinator doesn't need prose for all 61
    districts anyway, just the ones actually receiving significant aid.
    """
    prompt = (
        f"You are assisting a humanitarian coordinator allocating {resource_type} aid "
        "across districts in Syria, drawn from the real, currently 32%-funded 2026 "
        "Humanitarian Needs and Response Plan. For each district below, write one "
        "plain-language sentence (max 30 words) explaining WHY it received this "
        "allocation, citing its IDP population and existing organizational presence. "
        "Be specific to the numbers given, not generic.\n\n"
        "Districts:\n"
        + "\n".join(
            f"- admin2_code={d['admin2_code']}, name={d['admin2_name']} ({d['admin1_name']}), "
            f"idp_population={d['idp_population']}, active_org_count={d['active_org_count']}, "
            f"allocated_usd={d['quantity_allocated']:,.0f}"
            for d in top_districts
        )
        + '\n\nRespond with ONLY a JSON object mapping each admin2_code to its rationale '
        'sentence, e.g. {"SY0800": "..."}. No other text.'
    )
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    try:
        return json.loads(response.text)
    except (json.JSONDecodeError, TypeError):
        # Gemini free tier occasionally wraps JSON in prose despite the
        # mime type hint -- fail soft with empty rationale rather than
        # 500ing the whole allocation.
        return {}


class AllocationRequest(BaseModel):
    crisis_region: str = "SYR"
    resource_type: str  # 'food' | 'medicine' | 'shelter'
    top_n_rationale: int = 10


@app.post("/allocate")
def allocate(req: AllocationRequest):
    bq = get_bq_client()
    districts = fetch_district_need_scores(bq)
    if not districts:
        raise HTTPException(
            status_code=404,
            detail="No district need-score data in BigQuery yet — run "
            "bigquery/load_syria_data.sh then the views in bigquery/schema.sql first",
        )

    supply_pool = fetch_supply_pool(bq, SYRIA_APPEAL_CODE)
    districts = compute_proportional_allocation(districts, supply_pool)

    top = sorted(districts, key=lambda d: d["quantity_allocated"], reverse=True)[: req.top_n_rationale]
    rationale_by_code = generate_rationale(get_gemini_client(), top, req.resource_type)

    run_id = str(uuid.uuid4())
    fs = get_firestore_client()
    batch = fs.batch()
    results = []
    for d in districts:
        doc = {
            "allocation_id": f"{run_id}-{d['admin2_code']}",
            "run_id": run_id,
            "admin2_code": d["admin2_code"],
            "admin2_name": d["admin2_name"],
            "admin1_name": d["admin1_name"],
            "resource_type": req.resource_type,
            "idp_population": d["idp_population"],
            "active_org_count": d["active_org_count"],
            "need_score": d["need_score"],
            "quantity_allocated": d["quantity_allocated"],
            "rationale_text": rationale_by_code.get(d["admin2_code"], ""),
        }
        batch.set(fs.collection("allocations").document(doc["allocation_id"]), doc)
        results.append(doc)
    batch.commit()

    return {
        "run_id": run_id,
        "crisis_region": req.crisis_region,
        "resource_type": req.resource_type,
        "supply_pool_usd": supply_pool,
        "district_count": len(results),
        "allocations": results,
    }


@app.get("/allocations")
def list_allocations(resource_type: str | None = None, run_id: str | None = None):
    """Read-back endpoint for the frontend map/dashboard."""
    fs = get_firestore_client()
    query = fs.collection("allocations")
    if resource_type:
        query = query.where("resource_type", "==", resource_type)
    if run_id:
        query = query.where("run_id", "==", run_id)
    return {"allocations": [doc.to_dict() for doc in query.stream()]}

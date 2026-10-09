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
import time
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.cloud import bigquery, firestore
from google.genai import errors as genai_errors
from pydantic import BaseModel

# No-op in Cloud Run (env vars are injected directly there); picks up
# aidatlas-api/.env for local runs.
load_dotenv()

app = FastAPI(title="AidAtlas")

# Frontend (Firebase Hosting) and backend (Cloud Run) are different
# origins, so the browser needs explicit CORS clearance. Kept to a named
# allowlist rather than "*" since /allocate and /ask are real write/cost
# paths, not read-only public data.
ALLOWED_ORIGINS = [
    "https://ai-builder-cup-aidatlas.web.app",
    "https://ai-builder-cup-aidatlas.firebaseapp.com",
    "http://localhost:5000",
    "http://127.0.0.1:5000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# gemini-2.5-flash is deprecated for new callers as of this session --
# confirmed live from the API's own 404 error, which pointed us at this.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
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


QUOTA_EXHAUSTED = False  # set true on a 429 so later calls skip straight to fallback, no wasted retries


def call_gemini(client: genai.Client, prompt: str, json_mode: bool) -> str | None:
    """Shared retry/fallback wrapper for every Gemini call in this
    service. Two real failure modes confirmed live while building this,
    not hypothetical: transient 503s under Google's own load (worth
    retrying), and the free tier's hard daily quota -- confirmed to be
    just 20 requests/day for gemini-3.8-flash via a live 429, far
    tighter than the ~1,000+/day documented for the prior generation.
    A 429 won't resolve by retrying (the reset is hours away), so it
    fails fast to fallback rather than burning the retry budget. Either
    way, callers get None rather than a propagated 500 -- the submission
    rules require the deployed prototype to survive an unattended
    judging window, and BigQuery's numbers are real and useful even
    when Gemini's commentary on top of them isn't available.
    """
    global QUOTA_EXHAUSTED
    if QUOTA_EXHAUSTED:
        return None

    config = {"response_mime_type": "application/json"} if json_mode else {}
    last_error = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt, config=config)
            return response.text
        except genai_errors.ServerError as exc:
            last_error = exc
            time.sleep(2 * (attempt + 1))
        except genai_errors.ClientError as exc:
            if exc.code == 429:
                QUOTA_EXHAUSTED = True
                print(f"Gemini daily quota exhausted, switching to fallback mode: {exc}")
                return None
            raise
    print(f"Gemini call failed after retries: {last_error}")
    return None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/gemini-ping")
def gemini_ping():
    """Smoke-test the free-tier Gemini key end to end."""
    text = call_gemini(get_gemini_client(), "Reply with the single word: ready", json_mode=False)
    if text is None:
        raise HTTPException(status_code=503, detail="Gemini unavailable after retries")
    return {"model": GEMINI_MODEL, "reply": text}


def fetch_district_need_scores(bq: bigquery.Client) -> list[dict]:
    query = f"""
        SELECT admin1_name, admin2_name, admin2_code, idp_population,
               active_org_count, need_score, lat, lon
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


@app.get("/districts")
def list_districts():
    """All 61 districts with need-score and (where real data has it)
    coordinates, independent of any allocation run -- lets the frontend
    map render immediately on load. 48 of 61 have real coordinates,
    derived from food-price market locations; the rest come back with
    lat/lon null rather than a fabricated point.
    """
    bq = get_bq_client()
    districts = fetch_district_need_scores(bq)
    return {"district_count": len(districts), "with_coordinates": sum(1 for d in districts if d["lat"]), "districts": districts}


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
    text = call_gemini(client, prompt, json_mode=True)
    if text is None:
        return {}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        # Gemini occasionally wraps JSON in prose despite the mime type
        # hint -- fail soft, the allocation numbers aren't affected.
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
            "lat": d["lat"],
            "lon": d["lon"],
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


class AskRequest(BaseModel):
    question: str
    resource_type: str = "shelter"


@app.post("/ask")
def ask(req: AskRequest):
    """Natural-language challenge/question over the most recent real
    allocation -- "why not send more to district X" or "which district
    has the least coverage" -- answered by Gemini grounded strictly in
    the real numbers already sitting in Firestore, not invented. This is
    the coordinator-facing explainability feature the design centers on:
    every number the answer cites traces back to a real HDX figure.
    """
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    fs = get_firestore_client()
    docs = (
        fs.collection("allocations")
        .where("resource_type", "==", req.resource_type)
        .order_by("quantity_allocated", direction=firestore.Query.DESCENDING)
        .limit(20)
        .stream()
    )
    context_rows = [doc.to_dict() for doc in docs]
    if not context_rows:
        raise HTTPException(
            status_code=404,
            detail=f"No allocation run yet for resource_type={req.resource_type!r} — call /allocate first",
        )

    context_text = "\n".join(
        f"- {d['admin2_name']} ({d['admin1_name']}, code {d['admin2_code']}): "
        f"allocated ${d['quantity_allocated']:,.0f}, IDP population {d['idp_population']:,}, "
        f"{d['active_org_count']} organizations already active, need_score {d['need_score']:.1f}"
        for d in context_rows
    )
    total_allocated = sum(d["quantity_allocated"] for d in context_rows)
    prompt = (
        "You are AidAtlas, assisting a humanitarian coordinator reviewing a real "
        f"{req.resource_type} aid allocation across Syrian districts, drawn from the real "
        "2026 HSYR26 Humanitarian Needs and Response Plan (32% funded as of this appeal). "
        f"Below are the top {len(context_rows)} districts by allocation in the current run "
        f"(combined ${total_allocated:,.0f} of the total pool):\n\n{context_text}\n\n"
        f'Coordinator question: "{req.question}"\n\n'
        "Answer using ONLY the numbers above. If the question references a district not "
        "listed here, say plainly that it's outside the top districts shown rather than "
        "guessing at its figures. Be concise (under 90 words), specific, and cite real "
        "numbers from the list."
    )
    answer = call_gemini(get_gemini_client(), prompt, json_mode=False)
    if answer is None:
        # Real numbers, not an invented answer: give the coordinator the
        # same context Gemini would have reasoned over, rather than a
        # bare error, since the free tier's daily quota can genuinely
        # run out mid-demo (confirmed live, not hypothetical).
        answer = (
            "AI commentary is temporarily unavailable (Gemini's free-tier daily quota, or a transient "
            f"outage). Here are the real top {len(context_rows)} districts by allocation this run: "
            + "; ".join(f"{d['admin2_name']} ${d['quantity_allocated']:,.0f}" for d in context_rows[:5])
            + "."
        )

    return {"question": req.question, "resource_type": req.resource_type, "answer": answer, "districts_considered": len(context_rows)}

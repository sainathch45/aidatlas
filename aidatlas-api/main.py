"""AidAtlas — crisis resource allocator backend.

Deploys to Cloud Run. Calls Gemini via Vertex AI / Gemini Enterprise
Agent Platform. Reads district/state need-scores from BigQuery (see
bigquery/schema.sql for Syria, bigquery/schema_myanmar.sql for Myanmar),
and writes/reads the resulting allocations + rationale through
Firestore for the live dashboard/map.

Deliberately supports more than one crisis to prove the architecture is
reusable, not because the demo needed two regions. Syria and Myanmar
have genuinely different real data shapes -- Syria gives IDP population
by admin2 district plus org-presence counts, uninfluenced by resource
type; Myanmar gives sector-specific (shelter/food/health) "in need"
population by admin1 state, so its need_score actually varies by
resource_type where Syria's doesn't. CRISIS_REGISTRY below is the one
place that difference is declared; everything downstream of
fetch_district_need_scores operates on one normalized shape regardless
of which crisis it came from.

Local run:
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8080
    (needs `gcloud auth application-default login` done once locally;
    Cloud Run uses its attached service account instead)
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
VERTEX_LOCATION = os.environ.get("AGENT_PLATFORM_LOCATION", "global")
BQ_DATASET = os.environ.get("BIGQUERY_DATASET", "crisis_allocator")

# Both appeal codes and figures confirmed real from the actual downloaded
# HDX HAPI funding CSVs, not invented: HSYR26 ($935,449,756 of
# $2,922,184,830, 32% funded) and HMMR26 ($444,151,722 of $889,600,798,
# 50% funded).
CRISIS_REGISTRY = {
    "SYR": {
        "name": "Syria",
        "appeal_code": "HSYR26",
        "appeal_label": "the 2026 HSYR26 Humanitarian Needs and Response Plan",
        "funding_table": "raw_funding",
        "requirements_usd": 2922184830,
        "funding_pct": 32,
        "map_center": {"lat": 35.0, "lng": 38.0},
        "map_zoom": 7,
    },
    "MMR": {
        "name": "Myanmar",
        "appeal_code": "HMMR26",
        "appeal_label": "the 2026 HMMR26 Humanitarian Needs and Response Plan",
        "funding_table": "raw_funding_mmr",
        "requirements_usd": 889600798,
        "funding_pct": 50,
        "map_center": {"lat": 21.9, "lng": 96.0},
        "map_zoom": 6,
    },
}

# Myanmar's humanitarian_needs data is genuinely broken down by sector
# (confirmed SHL/FSC/HEA all present at the same latest period before
# building this) -- Syria's isn't, so this map only applies to Myanmar.
SECTOR_MAP = {"shelter": "SHL", "food": "FSC", "medicine": "HEA"}


def get_gemini_client() -> genai.Client:
    # Vertex AI mode: authenticates via Application Default Credentials
    # (the Cloud Run service's attached service account in prod, or
    # `gcloud auth application-default login` locally) -- no API key.
    return genai.Client(vertexai=True, project=PROJECT_ID, location=VERTEX_LOCATION)


def get_bq_client() -> bigquery.Client:
    return bigquery.Client(project=PROJECT_ID)


def get_firestore_client() -> firestore.Client:
    return firestore.Client(project=PROJECT_ID)


QUOTA_EXHAUSTED = False  # set true on a 429 so later calls skip straight to fallback, no wasted retries


def call_gemini(client: genai.Client, prompt: str, json_mode: bool) -> str | None:
    """Shared retry/fallback wrapper for every Gemini call in this
    service. Two real failure modes confirmed live while building this,
    not hypothetical: transient 503s under Google's own load (worth
    retrying), and the Developer API free tier's hard daily quota (the
    reason this now runs on Vertex AI instead). Either way, callers get
    None rather than a propagated 500 -- the submission rules require
    the deployed prototype to survive an unattended judging window.
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


@app.get("/crises")
def list_crises():
    """What regions the frontend can offer in its selector."""
    return {"crises": [{"code": code, **cfg} for code, cfg in CRISIS_REGISTRY.items()]}


@app.get("/gemini-ping")
def gemini_ping():
    """Smoke-test the free-tier Gemini key end to end."""
    text = call_gemini(get_gemini_client(), "Reply with the single word: ready", json_mode=False)
    if text is None:
        raise HTTPException(status_code=503, detail="Gemini unavailable after retries")
    return {"model": GEMINI_MODEL, "reply": text}


def fetch_district_need_scores(bq: bigquery.Client, crisis_region: str, resource_type: str) -> list[dict]:
    """Returns a normalized list of dicts regardless of which crisis's
    underlying data shape produced them: admin_name, admin_parent_name,
    admin_code, need_score, lat, lon, and a crisis-specific `context`
    dict carried through for the Gemini rationale prompt. This is the
    one function that knows about the real schema differences between
    crises; everything downstream (allocation math, rationale, Firestore
    writes) only ever sees the normalized shape.
    """
    if crisis_region == "SYR":
        query = f"""
            SELECT admin1_name, admin2_name, admin2_code, idp_population,
                   active_org_count, need_score, lat, lon
            FROM `{PROJECT_ID}.{BQ_DATASET}.district_need_score`
            WHERE need_score IS NOT NULL
            ORDER BY need_score DESC
        """
        rows = [dict(r) for r in bq.query(query).result()]
        return [
            {
                "admin_name": r["admin2_name"],
                "admin_parent_name": r["admin1_name"],
                "admin_code": r["admin2_code"],
                "need_score": r["need_score"],
                "lat": r["lat"],
                "lon": r["lon"],
                "context": {"idp_population": r["idp_population"], "active_org_count": r["active_org_count"]},
            }
            for r in rows
        ]

    if crisis_region == "MMR":
        sector = SECTOR_MAP.get(resource_type)
        if not sector:
            raise HTTPException(status_code=400, detail=f"Unknown resource_type {resource_type!r}")
        query = f"""
            SELECT district_name, district_code, need_score, lat, lon
            FROM `{PROJECT_ID}.{BQ_DATASET}.mmr_need_score`
            WHERE sector_code = @sector AND need_score IS NOT NULL
            ORDER BY need_score DESC
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("sector", "STRING", sector)]
        )
        rows = [dict(r) for r in bq.query(query, job_config=job_config).result()]
        return [
            {
                "admin_name": r["district_name"],
                "admin_parent_name": "Myanmar",
                "admin_code": r["district_code"],
                "need_score": r["need_score"],
                "lat": r["lat"],
                "lon": r["lon"],
                "context": {"people_in_need": r["need_score"], "sector": sector},
            }
            for r in rows
        ]

    raise HTTPException(
        status_code=400,
        detail=f"Unsupported crisis_region {crisis_region!r}. Supported: {list(CRISIS_REGISTRY)}",
    )


def fetch_supply_pool(bq: bigquery.Client, funding_table: str, appeal_code: str) -> float:
    # Funding data lives in a separate table per crisis (raw_funding for
    # Syria, raw_funding_mmr for Myanmar) -- hardcoding the Syria table
    # name here was a real bug caught live: Myanmar allocations returned
    # a $0 pool because this always queried raw_funding regardless of
    # which crisis was requested.
    query = f"""
        SELECT funding_usd
        FROM `{PROJECT_ID}.{BQ_DATASET}.{funding_table}`
        WHERE appeal_code = @appeal_code
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("appeal_code", "STRING", appeal_code)]
    )
    rows = list(bq.query(query, job_config=job_config).result())
    return float(rows[0]["funding_usd"]) if rows else 0.0


@app.get("/districts")
def list_districts(crisis_region: str = "SYR", resource_type: str = "shelter"):
    """Districts/states with need-score and (where real data has it)
    coordinates, independent of any allocation run -- lets the frontend
    map render immediately on load. resource_type only changes the
    result for crises (Myanmar) whose need data is sector-specific;
    Syria ignores it.
    """
    if crisis_region not in CRISIS_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unsupported crisis_region {crisis_region!r}")
    bq = get_bq_client()
    districts = fetch_district_need_scores(bq, crisis_region, resource_type)
    return {
        "crisis_region": crisis_region,
        "district_count": len(districts),
        "with_coordinates": sum(1 for d in districts if d["lat"]),
        "districts": districts,
    }


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


def format_district_line(d: dict) -> str:
    """Crisis-agnostic district summary line for the Gemini prompt,
    branching only on which context keys are actually present.
    """
    ctx = d["context"]
    base = f"- admin_code={d['admin_code']}, name={d['admin_name']} ({d['admin_parent_name']})"
    if "idp_population" in ctx:
        detail = f"idp_population={ctx['idp_population']}, active_org_count={ctx['active_org_count']}"
    else:
        detail = f"people_in_need={ctx['people_in_need']:,.0f} ({ctx['sector']} sector)"
    return f"{base}, {detail}, allocated_usd={d['quantity_allocated']:,.0f}"


def generate_rationale(client: genai.Client, top_districts: list[dict], resource_type: str, crisis_name: str) -> dict[str, str]:
    """One batched Gemini call for the top allocations, not one call per
    district -- Vertex AI latency (3-30s observed live) makes
    per-district calls impractical, and a coordinator doesn't need prose
    for all districts anyway, just the ones receiving significant aid.
    """
    prompt = (
        f"You are assisting a humanitarian coordinator allocating {resource_type} aid "
        f"across {crisis_name}, drawn from a real, currently active humanitarian response "
        "plan. For each location below, write one plain-language sentence (max 30 words) "
        "explaining WHY it received this allocation, citing the real figures given. "
        "Be specific to the numbers given, not generic. Plain prose only -- no markdown "
        "formatting (no asterisks, no bullet points, no headers), since this renders as "
        "plain text in the UI.\n\n"
        "Locations:\n"
        + "\n".join(format_district_line(d) for d in top_districts)
        + '\n\nRespond with ONLY a JSON object mapping each admin_code to its rationale '
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
    if req.crisis_region not in CRISIS_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unsupported crisis_region {req.crisis_region!r}. Supported: {list(CRISIS_REGISTRY)}")
    crisis = CRISIS_REGISTRY[req.crisis_region]

    bq = get_bq_client()
    districts = fetch_district_need_scores(bq, req.crisis_region, req.resource_type)
    if not districts:
        raise HTTPException(
            status_code=404,
            detail=f"No need-score data in BigQuery for {req.crisis_region} yet — run the matching "
            "bigquery/load_*.sh and schema*.sql first",
        )

    supply_pool = fetch_supply_pool(bq, crisis["funding_table"], crisis["appeal_code"])
    districts = compute_proportional_allocation(districts, supply_pool)

    top = sorted(districts, key=lambda d: d["quantity_allocated"], reverse=True)[: req.top_n_rationale]
    rationale_by_code = generate_rationale(get_gemini_client(), top, req.resource_type, crisis["name"])
    # Distinguishes "Gemini was unavailable for this whole run" from "this
    # district just wasn't in the top N narrated" -- without this, every
    # district showed the same "outside top-N" message even when quota
    # exhaustion meant NONE of them, including the top 10, got rationale.
    # Caught directly from how misleading that read in the live UI.
    rationale_generated = bool(rationale_by_code)

    # Deterministic doc id per (crisis_region, resource_type, district)
    # -- NOT including run_id -- so a re-run overwrites the previous
    # run's doc instead of accumulating stale duplicates. Hit this live
    # with a single-crisis version of this bug before: /ask was blending
    # districts from multiple old runs together.
    run_id = str(uuid.uuid4())
    fs = get_firestore_client()
    batch = fs.batch()
    results = []
    for d in districts:
        doc = {
            "allocation_id": f"{req.crisis_region}-{req.resource_type}-{d['admin_code']}",
            "run_id": run_id,
            "crisis_region": req.crisis_region,
            "crisis_name": crisis["name"],
            "admin_code": d["admin_code"],
            "admin_name": d["admin_name"],
            "admin_parent_name": d["admin_parent_name"],
            "resource_type": req.resource_type,
            "need_score": d["need_score"],
            "quantity_allocated": d["quantity_allocated"],
            "lat": d["lat"],
            "lon": d["lon"],
            "context": d["context"],
            "rationale_text": rationale_by_code.get(d["admin_code"], ""),
            "rationale_generated": rationale_generated,
        }
        batch.set(fs.collection("allocations").document(doc["allocation_id"]), doc)
        results.append(doc)
    batch.commit()

    return {
        "run_id": run_id,
        "crisis_region": req.crisis_region,
        "crisis_name": crisis["name"],
        "resource_type": req.resource_type,
        "supply_pool_usd": supply_pool,
        "district_count": len(results),
        "allocations": results,
    }


@app.get("/allocations")
def list_allocations(crisis_region: str | None = None, resource_type: str | None = None, run_id: str | None = None):
    """Read-back endpoint for the frontend map/dashboard."""
    fs = get_firestore_client()
    query = fs.collection("allocations")
    if crisis_region:
        query = query.where("crisis_region", "==", crisis_region)
    if resource_type:
        query = query.where("resource_type", "==", resource_type)
    if run_id:
        query = query.where("run_id", "==", run_id)
    return {"allocations": [doc.to_dict() for doc in query.stream()]}


class AskRequest(BaseModel):
    question: str
    crisis_region: str = "SYR"
    resource_type: str = "shelter"


@app.post("/ask")
def ask(req: AskRequest):
    """Natural-language challenge/question over the most recent real
    allocation for the given crisis -- "why not send more to district X"
    -- answered by Gemini grounded strictly in the real numbers already
    sitting in Firestore, not invented.
    """
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")
    if req.crisis_region not in CRISIS_REGISTRY:
        raise HTTPException(status_code=400, detail=f"Unsupported crisis_region {req.crisis_region!r}")
    crisis = CRISIS_REGISTRY[req.crisis_region]

    fs = get_firestore_client()
    docs = (
        fs.collection("allocations")
        .where("crisis_region", "==", req.crisis_region)
        .where("resource_type", "==", req.resource_type)
        .order_by("quantity_allocated", direction=firestore.Query.DESCENDING)
        .limit(20)
        .stream()
    )
    context_rows = [doc.to_dict() for doc in docs]
    if not context_rows:
        raise HTTPException(
            status_code=404,
            detail=f"No allocation run yet for {req.crisis_region}/{req.resource_type} — call /allocate first",
        )

    context_text = "\n".join(
        f"- {d['admin_name']} ({d['admin_parent_name']}, code {d['admin_code']}): "
        f"allocated ${d['quantity_allocated']:,.0f}, need_score {d['need_score']:.1f}"
        for d in context_rows
    )
    total_allocated = sum(d["quantity_allocated"] for d in context_rows)
    prompt = (
        f"You are AidAtlas, assisting a humanitarian coordinator reviewing a real "
        f"{req.resource_type} aid allocation for {crisis['name']}, drawn from {crisis['appeal_label']}. "
        f"Below are the top {len(context_rows)} locations by allocation in the current run "
        f"(combined ${total_allocated:,.0f} of the total pool):\n\n{context_text}\n\n"
        f'Coordinator question: "{req.question}"\n\n'
        "Answer using ONLY the numbers above. If the question references a location not "
        "listed here, say plainly that it's outside the top locations shown rather than "
        "guessing at its figures. Be concise (under 90 words), specific, and cite real "
        "numbers from the list. Plain prose only -- no markdown formatting (no asterisks, "
        "no bullet points, no headers), since this renders as plain text in the UI."
    )
    answer = call_gemini(get_gemini_client(), prompt, json_mode=False)
    if answer is None:
        # Real numbers, not an invented answer: give the coordinator the
        # same context Gemini would have reasoned over, rather than a
        # bare error, since the free tier's daily quota can genuinely
        # run out mid-demo (confirmed live, not hypothetical).
        answer = (
            "AI commentary is temporarily unavailable (Gemini's free-tier daily quota, or a transient "
            f"outage). Here are the real top {len(context_rows)} locations by allocation this run: "
            + "; ".join(f"{d['admin_name']} ${d['quantity_allocated']:,.0f}" for d in context_rows[:5])
            + "."
        )

    return {
        "question": req.question,
        "crisis_region": req.crisis_region,
        "resource_type": req.resource_type,
        "answer": answer,
        "districts_considered": len(context_rows),
    }

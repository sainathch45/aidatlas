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
        "mode": "hrp_grounded",
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
        "mode": "hrp_grounded",
        "appeal_code": "HMMR26",
        "appeal_label": "the 2026 HMMR26 Humanitarian Needs and Response Plan",
        "funding_table": "raw_funding_mmr",
        "requirements_usd": 889600798,
        "funding_pct": 50,
        "map_center": {"lat": 21.9, "lng": 96.0},
        "map_zoom": 6,
    },
    # "ai_drafted" mode: no formal UN Humanitarian Response Plan exists for
    # these (India self-manages disaster response, so it isn't in HDX
    # HAPI's 20-country HRP list), so there's no real appeal/funding
    # figure to split. Instead of a dollar allocation, this mode produces
    # a Gemini-drafted PRIORITY RANKING from real but non-standardized
    # public reporting (compiled in data/india_situation_briefing.json,
    # every figure cited), explicitly labeled as drafted, not official.
    "MHD": {
        "name": "Maharashtra (2026 El Nino Drought)",
        "mode": "ai_drafted",
        "map_center": {"lat": 18.9, "lng": 76.3},
        "map_zoom": 7,
    },
    "ASF": {
        "name": "Assam (2026 Floods)",
        "mode": "ai_drafted",
        "map_center": {"lat": 26.7, "lng": 94.3},
        "map_zoom": 8,
    },
}

_BRIEFING_PATH = os.path.join(os.path.dirname(__file__), "data", "india_situation_briefing.json")
with open(_BRIEFING_PATH, encoding="utf-8") as f:
    INDIA_BRIEFING = json.load(f)

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

    if crisis_region in ("MHD", "ASF"):
        # No BigQuery involved -- this data isn't a clean HDX export, it's
        # the hand-compiled, cited briefing in india_situation_briefing.json
        # (real figures, non-standardized format, no official funding
        # total to split). resource_type is accepted for API consistency
        # but doesn't change the result -- the underlying reporting isn't
        # broken down by sector the way Myanmar's is.
        briefing = INDIA_BRIEFING[crisis_region]
        return [
            {
                "admin_name": d["name"],
                "admin_parent_name": briefing["name"],
                "admin_code": f"{crisis_region}-{d['name'].upper().replace(' ', '_')}",
                "need_score": d["value"],
                "lat": d.get("lat"),
                "lon": d.get("lon"),
                "context": {
                    "metric_label": briefing["metric_label"],
                    "metric_value": d["value"],
                    "note": d.get("note", ""),
                    "sources": briefing["sources"],
                },
            }
            for d in briefing["districts"]
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
    elif "people_in_need" in ctx:
        detail = f"people_in_need={ctx['people_in_need']:,.0f} ({ctx['sector']} sector)"
    else:
        # ai_drafted mode: no dollar figure exists, so no allocated_usd --
        # cite the real metric this ranking is actually based on instead.
        detail = f"{ctx['metric_label']}={ctx['metric_value']}"
        if ctx.get("note"):
            detail += f" ({ctx['note']})"
    if d.get("quantity_allocated") is not None:
        return f"{base}, {detail}, allocated_usd={d['quantity_allocated']:,.0f}"
    return f"{base}, {detail}, priority_rank={d.get('priority_rank', '?')}"


def generate_rationale(
    client: genai.Client, top_districts: list[dict], resource_type: str, crisis_name: str, mode: str
) -> dict[str, str]:
    """One batched Gemini call for the top allocations, not one call per
    district -- Vertex AI latency (3-30s observed live) makes
    per-district calls impractical, and a coordinator doesn't need prose
    for all districts anyway, just the ones receiving significant aid.
    """
    if mode == "hrp_grounded":
        task = (
            f"You are assisting a humanitarian coordinator allocating {resource_type} aid "
            f"across {crisis_name}, drawn from a real, currently active humanitarian response "
            "plan. For each location below, write one plain-language sentence (max 30 words) "
            "explaining WHY it received this allocation, citing the real figures given."
        )
    else:
        # ai_drafted mode: no official plan or funding total exists for
        # this crisis (confirmed -- not in HDX HAPI's 20-country formal
        # HRP list). Gemini is drafting a PROPOSED priority order from
        # real but non-standardized public reporting, not citing an
        # official allocation -- the prompt has to make that distinction
        # explicit, or the output could misleadingly read as official.
        task = (
            f"You are drafting a PROPOSED, NON-OFFICIAL {resource_type} relief priority ranking "
            f"for {crisis_name}, based on real public reporting (cited figures below) since no "
            "formal government-coordinated response plan exists for this crisis yet. For each "
            "location below, write one plain-language sentence (max 30 words) explaining why it "
            "ranks where it does, citing the real figure given. Do not imply this is an official "
            "or funded allocation -- frame it as a draft recommendation only."
        )
    prompt = (
        task
        + " Be specific to the numbers given, not generic. Plain prose only -- no markdown "
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


def rank_by_need(districts: list[dict]) -> list[dict]:
    """ai_drafted mode: no real funding total to split, so no dollar
    allocation math -- just rank by the real metric and assign a
    priority_rank. quantity_allocated stays None throughout, which the
    frontend uses to tell this mode apart from the HRP-grounded one.
    """
    ordered = sorted(districts, key=lambda d: d["need_score"], reverse=True)
    for i, d in enumerate(ordered, start=1):
        d["priority_rank"] = i
        d["quantity_allocated"] = None
    return ordered


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
            detail=f"No need-score data for {req.crisis_region} yet — run the matching "
            "bigquery/load_*.sh and schema*.sql first",
        )

    if crisis["mode"] == "hrp_grounded":
        supply_pool = fetch_supply_pool(bq, crisis["funding_table"], crisis["appeal_code"])
        districts = compute_proportional_allocation(districts, supply_pool)
        top = sorted(districts, key=lambda d: d["quantity_allocated"], reverse=True)[: req.top_n_rationale]
    else:
        supply_pool = None
        districts = rank_by_need(districts)
        top = districts[: req.top_n_rationale]

    rationale_by_code = generate_rationale(get_gemini_client(), top, req.resource_type, crisis["name"], crisis["mode"])
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
            "priority_rank": d.get("priority_rank"),
            "lat": d["lat"],
            "lon": d["lon"],
            "context": d["context"],
            "rationale_text": rationale_by_code.get(d["admin_code"], ""),
            "rationale_generated": rationale_generated,
            "mode": crisis["mode"],
        }
        batch.set(fs.collection("allocations").document(doc["allocation_id"]), doc)
        results.append(doc)
    batch.commit()

    return {
        "run_id": run_id,
        "crisis_region": req.crisis_region,
        "crisis_name": crisis["name"],
        "mode": crisis["mode"],
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

    # Plain equality filters only (no order_by) -- avoids needing yet
    # another Firestore composite index per mode. Dataset sizes here are
    # small (at most 61 docs for Syria) so sorting the fetched set in
    # Python instead of in Firestore is trivial, not a real cost.
    fs = get_firestore_client()
    docs = (
        fs.collection("allocations")
        .where("crisis_region", "==", req.crisis_region)
        .where("resource_type", "==", req.resource_type)
        .stream()
    )
    all_rows = [doc.to_dict() for doc in docs]
    if not all_rows:
        raise HTTPException(
            status_code=404,
            detail=f"No allocation run yet for {req.crisis_region}/{req.resource_type} — call /allocate first",
        )

    if crisis["mode"] == "hrp_grounded":
        context_rows = sorted(all_rows, key=lambda d: d["quantity_allocated"], reverse=True)[:20]
        context_text = "\n".join(
            f"- {d['admin_name']} ({d['admin_parent_name']}, code {d['admin_code']}): "
            f"allocated ${d['quantity_allocated']:,.0f}, need_score {d['need_score']:.1f}"
            for d in context_rows
        )
        total_allocated = sum(d["quantity_allocated"] for d in context_rows)
        basis = (
            f"a real {req.resource_type} aid allocation for {crisis['name']}, drawn from "
            f"{crisis['appeal_label']}. Below are the top {len(context_rows)} locations by "
            f"allocation in the current run (combined ${total_allocated:,.0f} of the total pool)"
        )
    else:
        context_rows = sorted(all_rows, key=lambda d: d["priority_rank"])[:20]
        context_text = "\n".join(
            f"- {d['admin_name']} ({d['admin_parent_name']}, code {d['admin_code']}): "
            f"priority rank #{d['priority_rank']}, {d['context'].get('metric_label', 'metric')} "
            f"{d['context'].get('metric_value', d['need_score'])}"
            for d in context_rows
        )
        basis = (
            f"a DRAFT, NON-OFFICIAL {req.resource_type} relief priority ranking for {crisis['name']} "
            f"(no formal government-coordinated plan exists for this crisis). Below are the "
            f"{len(context_rows)} ranked locations, based on real but non-standardized public reporting"
        )

    prompt = (
        f"You are AidAtlas, assisting a humanitarian coordinator reviewing {basis}:\n\n{context_text}\n\n"
        f'Coordinator question: "{req.question}"\n\n'
        "Answer using ONLY the numbers above. If the question references a location not "
        "listed here, say plainly that it's outside the locations shown rather than "
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
        if crisis["mode"] == "hrp_grounded":
            summary = "; ".join(f"{d['admin_name']} ${d['quantity_allocated']:,.0f}" for d in context_rows[:5])
        else:
            summary = "; ".join(f"#{d['priority_rank']} {d['admin_name']}" for d in context_rows[:5])
        answer = (
            "AI commentary is temporarily unavailable (Gemini's free-tier daily quota, or a transient "
            f"outage). Here are the real top locations this run: {summary}."
        )

    return {
        "question": req.question,
        "crisis_region": req.crisis_region,
        "resource_type": req.resource_type,
        "answer": answer,
        "districts_considered": len(context_rows),
    }

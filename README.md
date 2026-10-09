# AidAtlas

**Google Cloud AI Builder Cup, JAPAC 2026 — Sustainability & Social Impact track**
Team Ctrl Alt Conquer — Command. Control. Conquer.

Gemini-grounded crisis resource allocation, built on real Humanitarian Data Exchange (HDX) data for Syria's 2026 Humanitarian Needs and Response Plan (HSYR26) — currently **32% funded** against $2,922,184,830 required.

**Live:**
- App: https://ai-builder-cup-aidatlas.web.app
- API: https://aidatlas-api-866617346749.asia-southeast1.run.app

## What it does

AidAtlas splits the real, currently-available $935,449,756 HSYR26 funding pool across 61 real Syrian districts, weighted by a need score (real IDP population, discounted by how many organizations are already active there, from HDX's operational-presence data) — then asks Gemini to write a plain-language, numbers-grounded rationale for each allocation. A coordinator can also challenge any result in natural language ("why not send more to district X?") and get an answer that cites only real figures already in the system, never invented ones.

The differentiating bet here isn't a fancier optimizer — it's **explainability over raw optimality**: every dollar allocated comes with a defensible reason a coordinator could show a donor or auditor, not just a number.

## Why this fits the brief

- **Problem Alignment & Impact**: real crisis (Syria 2026 appeal), real funding gap, real district-level displacement data — not a synthetic demo.
- **Technical Merit & Gen AI Implementation**: a real multi-service Google Cloud pipeline (BigQuery → Gemini → Firestore → Cloud Run → Firebase Hosting), not a single-call LLM wrapper. Gemini is used for structured, grounded generation (JSON-mode rationale, NL Q&A over real stored data) with production-hardened retry/fallback behavior discovered and fixed live during development (see commit history).
- **Innovation & Creativity**: explainability-first framing, natural-language "ask" interrogation of a live allocation, a command-ops UI built around the real data rather than a generic dashboard template.
- **UX**: dark command-console interface, Google Maps with real district coordinates (48/61 derived from HDX's own food-price market locations), live stat strip, resource-type switching, zero fabricated map points.

## Google Cloud stack actually used

| Service | What it does here |
|---|---|
| **Gemini** (Developer API, `gemini-3.8-flash`) | Generates per-district allocation rationale (batched, JSON mode) and answers natural-language coordinator questions, grounded in real Firestore data |
| **BigQuery** | Hosts the raw HDX tables and the `district_need_score` view (need = IDP population discounted by existing org presence) that the allocation model reads |
| **Firestore** | Live state store for every allocation run — what the frontend map and Ask feature read from |
| **Cloud Run** | Hosts the FastAPI backend (`aidatlas-api/`) |
| **Firebase Hosting** | Serves the frontend (`frontend/`) |
| **Google Maps JavaScript API** | District map, dark-styled, real coordinates |

## Repo layout

```
data/           HDX ingestion (data/fetch_hdx_dataset.py) -- the real Syria CSVs
bigquery/       Schema + views (schema.sql) + load script (load_syria_data.sh)
aidatlas-api/   FastAPI backend, deployed to Cloud Run; tests/ has the full suite
frontend/       Vanilla JS dashboard, deployed to Firebase Hosting
```

## Running it yourself

```
cd data && pip install -r requirements.txt && python fetch_hdx_dataset.py hdx-hapi-syr
bash ../bigquery/load_syria_data.sh
bq query --use_legacy_sql=false < ../bigquery/schema.sql

cd ../aidatlas-api
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env   # fill in GEMINI_API_KEY (see .env.example for the free-tier gotcha)
uvicorn main:app --reload --port 8080
```

Frontend: serve `frontend/` with any static file server, pointed at your backend via `frontend/config.js`.

## Tests

```
cd aidatlas-api
pip install -r requirements-dev.txt
pytest tests/ -v                                        # unit tests, no credentials needed
python tests/smoke_test_live.py <backend-url>            # full live endpoint coverage
python tests/e2e_flow.py <frontend-url> <screenshot-dir> # Playwright: load, allocate, click, ask
```

## Honest notes, not overclaimed

- 48 of 61 districts have real plotted map coordinates (derived from HDX's food-price market locations); the remaining 13 are listed in data, not given a fabricated point.
- Gemini's free tier caps at 20 requests/day for `gemini-3.8-flash` (confirmed live, not documented anywhere obvious beforehand) — both `/allocate` and `/ask` degrade gracefully to real BigQuery/Firestore numbers without Gemini commentary if that's exhausted, rather than failing.
- The allocation model is a simple, explainable proportional split by need score, not a constrained optimizer — a deliberate choice, see "Why this fits the brief" above.

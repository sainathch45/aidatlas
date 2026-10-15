# AidAtlas

**Google Cloud AI Builder Cup, JAPAC 2026 — Sustainability & Social Impact track**
Team Ctrl Alt Conquer — Command. Control. Conquer.

Gemini-grounded crisis resource allocation, built on real Humanitarian Data Exchange (HDX) data. Started as a single-crisis Syria allocator; now covers two real, active UN Humanitarian Response Plans (Syria, Myanmar) plus two Indian disasters (Maharashtra drought, Assam floods) with no formal HRP, handled as explicitly-labeled "AI-drafted, not official" plans instead.

**Live:**
- App: https://ai-builder-cup-aidatlas.web.app
- API: https://aidatlas-api-866617346749.asia-southeast1.run.app

## What it does

For Syria and Myanmar ("hrp_grounded" crises), AidAtlas splits the real, currently-available HSYR26/HMMR26 funding pool across real districts, weighted by a need score from real HDX data — then asks Gemini to write a plain-language, numbers-grounded rationale for each allocation.

For Maharashtra and Assam ("ai_drafted" crises, no official appeal exists), there's no funding pool to split, so `optimizer.py` runs a real OR-Tools CP-SAT constrained-dispatch model instead: a user-set capacity is allocated across districts weighted by need, a **road-chokepoint network multiplier** (real driving routes via the Google Routes API — a district that sits on the route to several others gets boosted), and an **access factor** capped by live Sentinel-1 SAR flood-extent detection (a badly flooded district can still receive some aid, never zero). Gemini's prompt is told to explain the solver's actual reasoning, not just narrate a rank.

A coordinator can also challenge any result in natural language ("why not send more to district X?") and get an answer that cites only real figures already in the system, never invented ones.

The differentiating bet here isn't a fancier optimizer alone — it's **explainability over raw optimality**, extended across two genuinely different data shapes (official funded appeals vs. no-appeal disasters) and two real solving strategies (proportional split vs. constrained dispatch), reused across crises rather than rebuilt per crisis.

## Why this fits the brief

- **Problem Alignment & Impact**: real crisis (Syria 2026 appeal), real funding gap, real district-level displacement data — not a synthetic demo.
- **Technical Merit & Gen AI Implementation**: a real multi-service Google Cloud pipeline (BigQuery → Gemini → Firestore → Cloud Run → Firebase Hosting), not a single-call LLM wrapper. Gemini is used for structured, grounded generation (JSON-mode rationale, NL Q&A over real stored data) with production-hardened retry/fallback behavior discovered and fixed live during development (see commit history).
- **Innovation & Creativity**: explainability-first framing, natural-language "ask" interrogation of a live allocation, a command-ops UI built around the real data rather than a generic dashboard template.
- **UX**: dark command-console interface, Google Maps with real district coordinates (48/61 derived from HDX's own food-price market locations), live stat strip, resource-type switching, zero fabricated map points.

## Google Cloud stack actually used

| Service | What it does here |
|---|---|
| **Gemini** (Vertex AI, `gemini-3.8-flash`, global endpoint) | Generates per-district allocation rationale (batched, JSON mode) and answers natural-language coordinator questions, grounded in real Firestore data. Migrated here from the plain Developer API after its 20/day free-tier quota was flagged as the single biggest live-demo risk — auth is ADC/service account, no API key |
| **BigQuery** | Hosts the raw HDX tables and the per-crisis need-score views that the allocation model reads |
| **Firestore** | Live state store for every allocation run — what the frontend map and Ask feature read from |
| **Cloud Run** | Hosts the FastAPI backend (`aidatlas-api/`) |
| **Firebase Hosting** | Serves the frontend (`frontend/`) |
| **Google Maps JavaScript API** | District map, dark-styled, real coordinates |
| **Google Routes API** | Real driving routes between districts, for the road-chokepoint network multiplier in the OR-Tools dispatch model (switched to this from OSM's Overpass API, which proved unreliable from this build environment) |
| **Earth Engine** | Live CHIRPS precipitation / MODIS NDVI anomalies (drought) and Sentinel-1 SAR flood-extent detection (floods) for the AI-drafted India crises |
| **OR-Tools** (not a managed GCP service, but part of the stack) | CP-SAT constrained-dispatch solver, `aidatlas-api/optimizer.py` |

## Repo layout

```
data/           HDX ingestion + satellite/road-chokepoint fetch scripts -- see data/README.md
bigquery/       Schema + views for both HRP crises (schema.sql, schema_myanmar.sql)
aidatlas-api/   FastAPI backend (main.py + optimizer.py), deployed to Cloud Run; tests/ has the full suite
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
cp .env.example .env   # fill in GCP_PROJECT_ID etc. -- auth is `gcloud auth application-default login`, no API key
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
- The Gemini Developer API's free tier capped at 20 requests/day for `gemini-3.8-flash` (confirmed live) -- this is why the app runs on Vertex AI now instead; both `/allocate` and `/ask` still degrade gracefully to real BigQuery/Firestore numbers without Gemini commentary if a quota or outage hits, rather than failing.
- The allocation model is a proportional split by need score for the two official-appeal crises (Syria, Myanmar) -- a deliberate explainability-first choice, see "Why this fits the brief" above. The two AI-drafted India crises use a real constrained OR-Tools solver instead, since there's no official funding pool to proportionally split in the first place.

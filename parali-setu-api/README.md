# Parali Setu — Backend

FastAPI service wiring three independent layers together (see
`docs/PARALI_SETU_PRD.md` at the repo root for the full spec):

- **Gemini** (`extraction.py`, `gemini_client.py`) — language in, language
  or a perception signal out. Extracts a structured listing from text or
  a voice transcript, reads an optional stubble-photo for a quality grade,
  parses negotiation counter-offers, and narrates results. Never computes
  a price or quantity.
- **OR-Tools** (`solver.py`) — a transportation-LP solver that does every
  price/quantity decision. The only file that touches money.
- **Firestore** (`firestore_store.py`) — the only state, read live by both
  the farmer and company frontends.

`speech.py` wraps Cloud Speech-to-Text (farmer voice in) and Cloud
Text-to-Speech (narration out, MP3). `forecast_pipeline.py` reads a
BigQuery ML forecast (trained via `bigquery/forecast_model.sql`) and
writes it into Firestore as an offline batch step — never called live.

## Running locally

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in GCP_PROJECT_ID etc. — see that file's comments
uvicorn main:app --reload
```

Needs `gcloud auth application-default login` once per machine (Vertex AI
Gemini, Firestore, Speech/TTS, and BigQuery all authenticate via ADC — no
API keys in this project, same as `aidatlas-api`).

## Tests

```bash
pytest                    # 28 mocked tests, no credentials needed, fast
python tests/live_smoke.py   # hits the real Gemini/Firestore/Speech/TTS APIs — needs ADC
```

`live_smoke.py` is deliberately not named `test_*.py` so plain `pytest`
never tries to run it without credentials.

## Seeding data

```bash
python seed_data.py        # writes seed/*.json + seed/forecast_training_corpus.csv locally
python seed_firestore.py   # loads the 5 demo companies + their standing demand into Firestore
```

Run `seed_firestore.py` once after any Firestore reset — the live
dashboard and `/listings` need real standing demand to match against, or
every new listing will say "no buyer matched yet." Deliberately does
*not* seed farmer listings (see the comment in that file for why — a
past version did and it silently ate all the demand capacity a live
demo submission needed).

Retraining the forecast after reseeding the historical corpus:

```bash
bq query --use_legacy_sql=false < bigquery/forecast_model.sql
python forecast_pipeline.py
```

## Deploying

```bash
gcloud run deploy parali-setu-api \
  --source . --project ai-builder-cup-aidatlas --region asia-southeast1 \
  --allow-unauthenticated \
  --set-env-vars GCP_PROJECT_ID=ai-builder-cup-aidatlas,GEMINI_MODEL=gemini-3.8-flash,AGENT_PLATFORM_LOCATION=global \
  --memory 1Gi --timeout 120
```

Live: https://parali-setu-api-866617346749.asia-southeast1.run.app
(`/health` for a quick check).

## Known gaps, honestly

- The farmer flow's "confirm/edit before submit" step from the PRD
  (Section 8.1.2) isn't built in the frontend yet — the extracted listing
  is shown back to the farmer, but there's no edit-then-resubmit UI, only
  single-shot submission. A real architecture addition, not a quick fix.
- `read_stubble_quality()`'s grade is genuinely noisy on ambiguous real
  photos (documented in `seed/reference_photos/ATTRIBUTION.md`) — by
  design it's a soft matching signal the solver can ignore, never a price
  input, so this is a known limitation, not a hidden one.

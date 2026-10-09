# Crisis Resource Allocator — Ctrl Alt Conquer

Google Cloud AI Builder Cup, JAPAC 2026 — Sustainability & Social Impact track.

Gemini generates a defensible, plain-language rationale for how aid (food, medicine, shelter) should be allocated across locations in a real crisis, on top of a real allocation model running over real HDX humanitarian data.

## Is free tier actually possible? (checked 2026-10-09)

Short answer: **yes for cost, with one unavoidable exception.** Every service below can run at $0 actual spend. The one thing that cannot be avoided is that Cloud Run — mandatory for this hackathon — requires a billing account with a payment method attached, even though you will not be charged as long as usage stays inside the Always Free quota (2,000,000 requests/month, far beyond what a demo needs).

| Service | Needs a card attached? | What you actually get free |
|---|---|---|
| Gemini Developer API (via AI Studio key) | No | Flash / Flash-Lite models only — Pro models were moved behind billing as of an April 2026 policy change. ~1,000–1,500 requests/day, 10–15 req/min. Plenty for a demo; use Flash for the reasoning layer. |
| Firestore (Firebase Spark plan) | No | 1 GiB storage, 50k reads/day, 20k writes/day, 20k deletes/day, 10 GiB egress/month. |
| Firebase Hosting (Spark plan) | No | Standard free static hosting quota. |
| BigQuery | No, if you stay in **Sandbox mode** | 1 TiB processed queries/month, 10 GiB storage — same limits as the billed free tier, just with tables auto-expiring after 60 days (fine for a 9-day build) and no streaming inserts. |
| Cloud Run | **Yes** | 2M requests/month, 360k GB-seconds, 180k vCPU-seconds free — but Google requires a Blaze (pay-as-you-go) billing account to deploy at all, by policy, independent of hackathon credits. |
| Cloud Functions | Yes (Blaze) | Not needed — Cloud Run covers the backend requirement, skip this entirely. |
| HDX data access | No, ever | Fully open reads, no account or token needed for downloading datasets. |

**Open question for the two of you:** do either of you have a credit/debit card you're willing to attach to a fresh GCP project? This is a Google account-verification requirement, not an expected cost — but it is non-negotiable for Cloud Run, which the submission rules require by name. Everything else in this repo can be built and tested today without resolving this.

## Dataset: HDX, no synthetic data needed for the core signal

[HDX HAPI](https://data.humdata.org/hapi) (the Humanitarian Data Exchange's harmonized API) standardizes food security, displacement, and funding indicators across ~25 real humanitarian operations — exactly the three resource-adjacent signals this project needs, already aligned to the same locations. No account needed; reading it requires only a free `app_identifier` (see `data/README.md`).

Rather than guess at the beta API's exact endpoint paths, the ingestion script here starts from HDX's own **pre-packaged per-country HAPI CSV exports** — confirmed live dataset pages exist for at least Syria (`hdx-hapi-syr`), Iraq (`hdx-hapi-irq`), Haiti (`hdx-hapi-hti`), Ethiopia (`hdx-hapi-eth`), and Somalia (`hdx-hapi-som`). Pick one (criteria below), download via the standard CKAN API (no auth), and the live HAPI API becomes an optional upgrade later for fresher data.

**How to pick the region:** open each candidate's dataset page on data.humdata.org, and prefer whichever has location data down to admin1/admin2 (state/province) level with recent (last 6–12 months) food security and displacement figures — that granularity is what makes the allocation model's "locations" meaningful instead of one giant national blob.

## Repo layout

```
data/           HDX ingestion — run first, needs zero cloud setup
bigquery/       Schema for the allocation model's source tables
aidatlas-api/   FastAPI service — becomes the Cloud Run deployment
```

## Setup order

1. **Today, no account needed:** run `data/fetch_hdx_dataset.py` against one or two candidate country datasets, inspect the real CSV columns, confirm the region choice.
2. **Today, no card needed:** get a free Gemini API key at [aistudio.google.com](https://aistudio.google.com) — works immediately on the free tier.
3. **Today, no card needed:** create a Firebase project at [console.firebase.google.com](https://console.firebase.google.com) on the Spark (free) plan; enable Firestore.
4. **Today, no card needed:** in the Google Cloud Console, open BigQuery for the same project and start in Sandbox mode; load the real CSV once step 1 confirms the schema.
5. **Blocked on the card question above:** upgrade the project to Blaze and deploy `aidatlas-api/` to Cloud Run. Nothing else in the build depends on this happening first — do it whenever the card question is resolved.

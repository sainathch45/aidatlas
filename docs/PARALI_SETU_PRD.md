# Parali Setu — Product Requirements Document

**Status:** Draft v3, 2026-10-13 — v2 scored *lower* (59/100) than v1 (63/100) on re-eval, because v2 added explanation around the existing scope instead of cutting it, and introduced a direct self-contradiction in §13.1 (claimed the forecast hedge was "locked" one sentence before describing that exact hedge). v3 fixes the substance, not just the wording: cut one integration (§12 — Firestore realtime listeners replace Pub/Sub+FCM, same live UX, one fewer service), removed the self-contradiction in §13.1 outright, gave the ARIMA forecast a real, separately-sized training corpus instead of implying it trains on the tiny live-demo seed set (§11, §12), added an actual dashboard layout instead of more bullets (§8.2), and replaced §7.1's generic flywheel language with one specific, falsifiable mechanism. Parallel exploration branch (`parali-setu`) — does **not** replace the AidAtlas (Crisis Resource Allocator) submission on `master`. The team will decide between them after this revision is judge-evaluated again.

**Rule for implementation:** this PRD is the governing spec. No code is written against it until the user explicitly says to start. Any deviation during build must be flagged and confirmed, not silently substituted.

---

## 1. Problem statement (official track text, verbatim)

**Track:** Sustainability & Social Impact

> Build an AI-powered solution that addresses a meaningful environmental or societal challenge. Solutions may focus on improving resource efficiency, increasing accessibility, strengthening resilience, supporting communities, or enabling more informed and sustainable decision-making.

**Suggested solution directions:** Climate and environmental intelligence, disaster preparedness, sustainable agriculture, resource optimization, accessibility, community services, waste reduction.

**Suggested Google Cloud technologies:** Gemini on Vertex AI for reasoning and natural-language interfaces, BigQuery for analysing large environmental or social datasets, Vertex AI for predictive models, Earth Engine for geospatial/environmental analysis where applicable, Cloud Storage for datasets and imagery, Vision AI or image analysis capabilities, Cloud Run for deploying applications, Pub/Sub for event-driven alerts or workflows.

## 2. Judging rubric (identical weights across all 6 tracks)

| Criterion | Weight |
|---|---|
| Technical Merit & Gen AI Implementation | 40% |
| Problem Alignment & Impact | 25% |
| Innovation & Creativity | 25% |
| User Experience & Solution Design | 10% |

## 3. Mandatory eligibility constraints

- Must use a Google AI model family (Gemini or Gemma) or be built on an agentic platform (Agent Platform / Antigravity / AI Studio).
- Must be deployed on Google Cloud via Cloud Run or Firebase. Non-Google cloud stacks are not eligible.
- Written submission must explicitly name **Firebase, Firestore, Cloud Run, and Gemini** — not just "Google AI + cloud" in the abstract.
- All materials (code, docs, presentation) in English.

## 4. One-liner

Parali Setu is a live matching system that connects farmers holding crop stubble with companies that turn it into packaging, cutlery, biofuel pellets, and road material — making selling the stubble faster and more certain than burning it, inside the farmer's narrow post-harvest window.

## 5. Theory of change — why this isn't just an advisory chatbot

Farmers in Punjab/Haryana have roughly 10–15 days between harvesting rice and sowing the next crop. Burning is free and takes a day; every alternative costs money or time they don't have. Giving a farmer advice doesn't stop a fire — only a buyer who shows up faster and more reliably than burning, inside that same window, does. The product's core job is therefore **matching speed and certainty**, not information delivery. The AI layer (Gemini) is the interface to that matching system, not a substitute for it.

**Scale, for context:** Punjab's paddy residue volume is commonly reported by state agriculture-department estimates in the 15–20 million tonnes/season range, and CPCB and SAFAR-India monitoring during the October–November burning season has repeatedly linked it to sharp PM2.5 spikes in Delhi-NCR. The mechanism this PRD depends on — a narrow sowing window driving the burn-or-sell decision — doesn't hinge on the exact figure; the precise number is a one-line citation check against the latest CPCB/SAFAR report before the deck ships, not an open question about whether the problem is real.

**Path beyond simulation:** the MVP's matching and transaction records (§10) are modeled so a real counterpart — one willing residue-aggregator or packaging company — could be plugged in post-hackathon without a schema change, turning the simulated `pending_pickup`/`completed` status flow into a real one. This isn't built for the hackathon, but the data model doesn't block it either.

## 6. Users & personas

- **Farmer** — Punjab/Haryana, post-harvest, speaks Hindi or Punjabi, variable literacy, uses a shared/basic smartphone. Needs voice-first interaction and a fast, trustworthy answer: who buys, at what price, when do they come.
- **Company buyer** — procurement/ops staff at a residue-offtake business (pellet plant, stubble-based packaging unit, biofuel producer). Needs to know what supply is coming, what to offer for it, and what to manufacture/where to sell for the season.
- **Out of scope for MVP (roadmap only):** government/NGO monitoring dashboards, logistics/trucking providers as a distinct user type.

## 7. Scope decisions — resolving the gaps already raised

| Gap raised | Resolution |
|---|---|
| Idea bundled three separate products (advisory, marketplace, company consulting) | Ship **one** integrated flow — listing → match → company recommendation — not three disjoint tools. |
| Full agronomy advice (which crop/fertilizer to plant) carries real-world liability and needs data we don't have | **Out of MVP scope.** Advice is limited to stubble disposal logistics and price — never crop/fertilizer recommendations. |
| "Isn't this just another offtake marketplace that already exists?" | Differentiator is the **live AI-mediated bilingual matching + deterministic pricing**, not the marketplace concept itself — argued explicitly in §7.1, not just asserted. |
| Live vs. batch matching | **Live** — the solver re-runs on every new listing or demand update, not on a schedule. |
| Dataset availability | Hybrid: synthetic farmer/company records, calibrated against real public reference data (district residue estimates, Agmarknet prices), clearly labeled as synthetic in the demo. |
| Voice input scope (decided 2026-10-13) | **In scope for MVP**, not a stretch goal — Speech-to-Text/Text-to-Speech is a core feature from the start. |
| Transaction/logistics scope (decided 2026-10-13) | **Simulated** confirm-pickup / confirm-payment step is in MVP. No real money or trucking integration — status fields only, clearly labeled in UI and pitch as simulated. |
| Project status (decided 2026-10-13) | Parallel branch (`parali-setu`); `master`/AidAtlas untouched; decision deferred until after judge-eval and team review. |

### 7.1 Competitive landscape & defensibility (locked 2026-10-13)

Three existing approaches already touch this problem, and each has a specific gap this product closes:

1. **Government Crop Residue Management (CRM) subsidy schemes** — subsidize machinery (balers, super seeders) but don't guarantee a farmer a time-bound buyer; application-based, not language-accessible, and silent on where the residue actually goes afterward.
2. **Offline residue aggregators / depots** — a company sets up a local collection point, but discovery and pricing happen manually, farmer-to-depot, with no live competition between buyers and no structured intake for a non-literate, Hindi/Punjabi-only farmer.
3. **Generic agri-advisory chatbots** — give static advice (what to plant, how to treat a pest) with no transactional engine behind them; nothing to match against, nothing that pays the farmer.

None of the three does **live, multi-buyer, price-discovering matching with a bilingual voice front end** — but that alone isn't a durable moat, since any of the three could bolt on a chatbot. The specific mechanism that's harder to copy quickly: every completed match (§10 `matches` collection) records an actual agreed price, quantity, and location against a listing the solver proposed. That accumulated record is what the solver's pricing logic and the BigQuery ML forecast (§12) are tuned against over time — a competitor launching the same bilingual front end on day one still starts with zero matched-transaction history to tune a solver or a forecast against. The advantage isn't "we have AI," it's a growing dataset of real local price/quantity/outcome triples that only accumulates by actually running live matches, not by copying the interface.

## 8. Core user flows

### 8.1 Farmer flow
1. Farmer opens the app, picks Hindi or Punjabi, speaks or types a stubble listing.
2. If spoken: Cloud Speech-to-Text transcribes it; Gemini extracts a structured record — `{quantity, unit, village/district, crop type, ready_by date, contact}` — and shows it back for a one-tap confirm/edit (guards against transcription errors).
3. Listing is written to Firestore.
4. The solver (OR-Tools on Cloud Run) re-runs matching against all open company demand the moment the listing lands.
5. Gemini composes the result — buyer, price per quintal, pickup window — as text and Text-to-Speech audio, in the farmer's language.
6. Farmer confirms interest → match status moves to `pending_pickup` (simulated, no real payment moves).
7. Farmer marks `picked_up` to close the loop (simulated).

### 8.2 Company flow
1. Company logs in (Firebase Auth) and sets/updates standing demand: capacity, price ceiling, quality spec, plant location, product lines.
2. Dashboard layout (English, desktop-first — procurement staff assumed to work from a desk, unlike the farmer's mobile/voice-first flow):

   ```
   ┌─────────────────────────────┬───────────────────────────┐
   │ INCOMING SUPPLY              │ RECOMMENDATION              │
   │ sorted by price × proximity, │ "Prioritize: disposable     │
   │ descending, updates live via │  plates — target Gujarat"   │
   │ a Firestore listener on      │ basis: pre-Navratri demand  │
   │ listings matched to this     │ forecast (§12), one card    │
   │ companyId                    │ per active period           │
   │ 12 qtl · ₹9/kg · 4km · ...   │                              │
   │ 8 qtl  · ₹8/kg · 11km · ...  │                              │
   ├─────────────────────────────┴───────────────────────────┤
   │ ACTIVE MATCHES (read-only status board, not drag-to-move) │
   │ proposed(2) → confirmed(1) → pending_pickup(3) → completed│
   ├─────────────────────────────────────────────────────────┤
   │ STANDING DEMAND  [capacity] [price ceiling] [quality] ... │
   └─────────────────────────────────────────────────────────┘
   ```

   Status changes (accept, mark received) happen via the Active Matches board; the Incoming Supply and Recommendation panels are read-only views driven by Firestore listeners, not editable here.
3. Company accepts a proposed match → farmer is notified → simulated transaction record created.
4. Company marks `received` to close the loop (simulated).

## 9. System architecture

```mermaid
flowchart LR
  F["Farmer\nvoice/text, Hindi/Punjabi"] --> STT["Cloud Speech-to-Text"]
  STT --> G1["Gemini\nextract listing"]
  G1 --> FS[("Firestore\nlistings, demand, matches")]
  C["Company\ndemand + capacity"] --> FS
  BQ[("BigQuery ML\nseasonal forecast")] --> OR
  FS --> OR["OR-Tools solver\non Cloud Run"]
  OR --> FS
  FS --> G2["Gemini\nexplain match"]
  G2 --> TTS["Cloud Text-to-Speech"]
  TTS --> F
  G2 --> C
```

Everything left of the solver is language (Gemini + STT/TTS). Everything through the solver is arithmetic (OR-Tools + BigQuery ML). They never swap jobs — Gemini never computes a price or quantity; the solver never generates language. The BigQuery ML box runs once, offline, during data seeding on the dedicated historical series (§11) — not as a live call during the demo; forecasts are read from Firestore like any other stored record (§12, §13.1). Dashboards and the farmer app pick up changes to that Firestore data directly via realtime listeners — this diagram has no separate messaging layer because none is needed (§12).

## 10. Data model (Firestore collections)

| Collection | Key fields |
|---|---|
| `farmers/{farmerId}` | name, phone, preferred_language, village, district |
| `listings/{listingId}` | farmerId, quantity_kg, crop_type, village, district, ready_by, status (`open`/`matched`/`pending_pickup`/`picked_up`), language |
| `companies/{companyId}` | name, location, capacity_kg_per_week, price_ceiling_per_kg, quality_spec, product_lines[] |
| `demand/{demandId}` | companyId, product, quantity_needed_kg, price_offer_per_kg, valid_until |
| `matches/{matchId}` | listingId, demandId, farmerId, companyId, price_agreed_per_kg, quantity_kg, status (`proposed`/`confirmed`/`pending_pickup`/`completed`), created_at |
| `forecasts/{forecastId}` | companyId or region, product, period, predicted_demand, generated_at |

## 11. Datasets

| Dataset | Type | Source & license |
|---|---|---|
| Farmer stubble listings (qty, district, crop, ready-by) | Synthetic | Generated for the demo; volumes shaped to published district residue estimates (below). |
| Company demand (capacity, price, location, product) | Synthetic | Generated for the demo, modeled on known residue-offtake businesses. |
| District crop-residue volume baseline | Real, reference only | Punjab Remote Sensing Centre / ICAR-CRIDA public residue reports — Government of India, public data. Used to calibrate synthetic volumes, not queried live. |
| Mandi price reference | Real, usable live | Agmarknet API, data.gov.in — Open Government Data License (India). Stretch goal: live price sanity-check. |
| Festival demand calendar (for product-mix forecasting) | Synthetic | Generated for the demo, patterned on documented festival shopping seasonality (Navratri, Diwali). |
| District boundaries | Real, reference only | India district GeoJSON, public-domain government survey data, permissively republished. |
| Historical seasonal demand series (forecast training corpus) | Synthetic | ~2 synthetic years, weekly observations (~104 points) per product/region series — distinct from and larger than the small live-demo seed set in §15, so the ARIMA_PLUS fit (§12) isn't trained on a handful of rows. |

## 12. Tech stack

| Component | GCP service | Role |
|---|---|---|
| Farmer & company language interface | Gemini API (Vertex AI) | Extracts structured listings from natural language; explains matches. Never does arithmetic. |
| Voice I/O | Cloud Speech-to-Text, Cloud Text-to-Speech | Converts farmer speech to text and responses back to speech, Hindi/Punjabi. |
| Matching & pricing engine | OR-Tools on Cloud Run | Solves the live farmer-to-company assignment; the only component that touches money/quantity math. |
| Seasonal demand forecast | BigQuery ML (ARIMA_PLUS) | Trained once during data seeding on the ~104-point-per-series synthetic history (§11) — not the small live-demo seed set; forecast rows are read from Firestore at runtime, not called live during the demo. |
| Live data store | Firestore | Listings, demand, matches, simulated transaction status. |
| Backend hosting | Cloud Run | Hosts the API tying Gemini, STT/TTS, the solver, and Firestore together. |
| Frontend | Firebase Hosting | Farmer and company web dashboards. |
| Live updates | Firestore realtime listeners | Dashboards and farmer app subscribe directly to Firestore document changes for "live" supply/match updates — no separate messaging service to deploy. |
| Login | Firebase Authentication | Separate farmer and company accounts. |

## 13. Non-functional requirements & risks

- **Uptime:** prototype must stay functional through the entire evaluation window with no retries allowed if down — deploy Cloud Run with a minimum instance count to avoid cold-start failures during judging.
- **No fabricated numbers:** if a Gemini call fails, show a plain error — never let the model guess a price or quantity. The solver is the single source of truth for all numbers.
- **No real money or logistics:** every "confirm" action is a Firestore status change, explicitly labeled as simulated in both the UI copy and the pitch, to avoid implying real payment/fintech functionality that isn't built.
- **Voice accuracy:** rural/accented Hindi/Punjabi speech may transcribe imperfectly — mitigated by the confirm/edit step after transcription (step 8.1.2) before a listing is submitted.
- **Language coverage:** Hindi + Punjabi for farmers; English for company-side (procurement staff assumed fluent).

### 13.1 Risk mitigation / contingency (internal — not a pitch claim)

- **Forecast component:** fitting ARIMA_PLUS on a ~104-point synthetic series (§11) is a batch job measured in minutes, done during data seeding, well before any demo rehearsal — there is no live dependency and no plausible build-time failure mode left to hedge against. This is the one component this PRD treats as fully closed, not contingent on anything.
- **Voice I/O failure during judging:** the demo script (§16) carries a scripted recovery step. If live transcription misfires, the presenter falls back to the confirm/edit path already built into the farmer flow (§8.1.2) and narrates it as the designed safety net, not an error. A second, pre-recorded clean take of the same voice interaction is held in reserve as the literal fallback if live input fails twice.
- **Live-service surface:** the MVP integrates eight GCP services (down from nine in v1/v2 — §12 dropped Pub/Sub+FCM for Firestore listeners, which the frontend already needs for live updates regardless). The forecast is off the live path entirely (above). The solver and the Gemini/STT/TTS loop are the only pieces still live during the actual demo, and they're also the two things the pitch is actually claiming credit for — everything else is infrastructure, not a claimed capability.

## 14. Success metrics mapped to judging criteria

- **Technical Merit & Gen AI (40%):** live Gemini + STT/TTS loop, a deterministic OR-Tools solver that re-runs live on every new listing, and a BigQuery ML forecast trained on a real ~104-point-per-series corpus (§11, §12) rather than the small live-demo seed set — eight integrated services total, down to the two that actually run live during judging (§13.1).
- **Problem Alignment & Impact (25%):** direct, concrete tie to stubble burning and Delhi air quality (§5); a specific causal lever (speed + certainty beating burning), not a generic climate dashboard, plus a stated path from simulated to real transactions (§5).
- **Innovation & Creativity (25%):** Gemini-as-interface + OR-Tools-as-decision-engine hybrid, not a pure LLM wrapper; dual-sided (farmer + company) product from one matching core; see §7.1 for the specific accumulated-transaction-data mechanism, not a generic flywheel claim.
- **UX & Solution Design (10%):** bilingual voice-first farmer experience (§8.1), a laid-out company dashboard with a defined interaction model (§8.2), one cohesive flow rather than three disjoint tools.

## 15. MVP cut vs. stretch goals

**MVP (what gets demoed):**
- Farmer flow steps 1–7, voice + text, Hindi + Punjabi.
- Company flow steps 1–4, including the simulated confirm-pickup/confirm-payment step.
- Live solver re-run triggered by each new listing.
- One seasonal forecast example surfaced on the company dashboard (e.g., pre-Navratri plate demand in Gujarat), generated offline from the ~104-point historical corpus (§11) — not from the small live-demo dataset below.
- Synthetic seed dataset for the *live demo* itself: roughly 15–20 farmer listings, 5 companies. This is separate from the larger historical corpus used only to train the forecast (§11, §12).

**Stretch (only if time remains):**
- Live Agmarknet price feed as a real-time sanity-check on offered prices.
- Map view of active matches.
- Multi-turn negotiation (farmer counter-offer).
- Additional regions/languages beyond Punjab/Haryana and Hindi/Punjabi.

## 16. Demo script outline (3–4 minute video)

1. **0:00–0:30** — Problem cold open: stubble burning and Delhi smog, framed concretely.
2. **0:30–1:30** — Farmer flow, live: speak a listing in Punjabi, watch Gemini extract it, watch a match and price appear within seconds. *Scripted fallback (§13.1): if transcription misfires, the presenter narrates the built-in confirm/edit step as the designed safety net — not a visible failure — with a pre-recorded clean take held in reserve.*
3. **1:30–2:30** — Company dashboard: incoming supply, forecast-driven manufacturing/market recommendation, accept a match.
4. **2:30–3:15** — One architecture slide: Gemini/STT/TTS vs. OR-Tools vs. BigQuery ML split.
5. **3:15–3:45** — Impact framing and close.

## 17. Open items for implementation kickoff (not yet decided — raise before coding starts)

- Exact synthetic seed dataset size/composition beyond the MVP cut's rough numbers.

*(The forecast-model choice that was open here in v1 is now locked — see §12 and §13.1. Resolving that hedge was itself a direct fix from the 2026-10-13 judge-eval.)*

## 18. Branching & workflow

- Branch: `parali-setu`, created off `master`. AidAtlas (`aidatlas-api/`, `frontend/`, `data/`) is untouched on this branch and on `master`.
- **No implementation code is written against this PRD until the user explicitly says to start.**
- This PRD is the governing spec for that implementation once it starts; deviations must be flagged and confirmed, not silently substituted.

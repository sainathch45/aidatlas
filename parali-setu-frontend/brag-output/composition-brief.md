# Hyperframes Composition Brief: Parali Setu

## Objective
Create a cinematic, trailer-scale brag video for Parali Setu — scaled to 180 seconds per explicit user request (the hackathon's required demo-video length), overriding the skill's native 15-25s default.

## Output
- Composition directory: `composition/`
- Rendered video: `brag.mp4`
- Format: landscape — 1920x1080
- Duration: 180 seconds

## Source Material
- Project root: `parali-setu-frontend/` (index.html, company.html, styles.css, app.js) and `parali-setu-api/` (solver.py, extraction.py, main.py, forecast_pipeline.py), per `docs/PARALI_SETU_PRD.md`
- Primary files read: `index.html`, `company.html`, `styles.css`, `company.js`, `PARALI_SETU_PRD.md`
- Product name: Parali Setu
- Tagline / strongest claim: "Parali. Stubble. Setu. Bridge. A live match between farmers who have it, and buyers who'll pay for it — before it burns."
- Key UI/visual moments recreated: the farmer match-card (`.match-row` label/value fields from `styles.css`), the company `.rec-card` recommendation block, the Punjabi voice transcript + language toggle
- Copy that appears verbatim: match-card field labels (QUANTITY/CROP/BUYER/PRICE/PICKUP BY), the real rec-card headline text pattern from `company.js`'s `renderRecommendation()`, the real negotiation placeholder copy from `index.html`

## Creative Direction
- Tone preset: cinematic
- Creative direction: a grounded climate-tech launch film — real social-impact stakes treated with trailer-scale seriousness, no jokes at the subject's expense
- Interpretation: big full-bleed type, dramatic wipes/crossfades, confident holds scaled up from the tone's native 3-5s/scene to accommodate 180s total
- Angle: open on the real, specific stake (Punjab's stubble-burning smoke and its Delhi air-quality consequence) before revealing the product as the answer, then prove it with the actual live flow rather than marketing copy
- Hook: "EVERY OCTOBER, PUNJAB'S SKY TURNS TO SMOKE."
- Outro / punchline: "SELLING. NOT BURNING." → wordmark → tagline → URL
- Avoid: generic SaaS language, abstract filler visuals, redesigning the product's real visual identity

## Visual Identity
- Background: `#fbfaf7`
- Surface: `#ffffff`
- Text/ink: `#201c14`, soft ink `#5c5648`
- Accent: `#b8651f`, soft accent fill `#faeadb`
- Display font: Fraunces (500/600, local TTF, no CDN)
- Mono/label font: IBM Plex Mono (400/500, local TTF, no CDN)
- Visual references: the real match-card and rec-card field layouts, the real wordmark (🌾 + "Parali Setu" in Fraunces)

## Storyboard
Full storyboard with beat-by-beat timing, text, and audio intent lives in `brag-plan.md`. Scene summary:
1. The hook — 15s — smoke gradient + cold-open line
2. The real scale — 15s — the 15-20M tonne stat + human reason
3. Product reveal — 15s — wordmark + tagline
4. Farmer flow, part 1 — 20s — Punjabi voice transcript typing out
5. Farmer flow, part 2 — 20s — match-card fields landing in sequence
6. Negotiation proof — 15s — live price tick ₹8.68 → ₹9.50
7. Company forecast — 18s — real BigQuery ML rec-card
8. Three capability claims — 24s (3×8s) — Gemini / OR-Tools / BigQuery ML
9. Turn back + outro — 38s — sky clears, wordmark returns, URL, credit line

## Audio
- Audio role: cinematic support, steady bed with reserved big hits at genuine turns
- Audio arc: low fade-in under the hook → lift at the product reveal → steady through the live-flow proof scenes → settle slightly for the capability claims → swell into the outro → long fade to silence
- Music: `happy-beats-business-moves-vol-12-by-ende-dot-app.mp3` (117.36s — shorter than the 180s runtime, so two overlapping clips crossfade around 115-118s to cover the full video, each with its own clip-local `data-automation` volume lane)
- Audio-reactive treatment: not implemented in this v1 pass (scoped out for time; a reasonable v2 addition per `audio.md`'s guidance — subtle RMS-driven warmth on the sky/card surfaces)
- Audio-coupled moments: per-character transcript typing (scene 4), five sequential match-card field reveals (scene 5), the live price tick (scene 6), the rec-card drop (scene 7), the outro logo bell (scene 9)
- SFX selection: `impactBell_heavy_000` on the product reveal, `impactBell_heavy_003` on the outro, `card-place-1` on each match-card field, `click_001` on the negotiation send, `drop_001` on the rec-card arrival
- Audio files: copied into `composition/assets/music/` and `composition/assets/sfx/{impact,casino,interface}/`

## Hyperframes Implementation Notes
- Monolithic single-file composition (`composition/index.html`), not split into sub-compositions — `lint` flags this as a style preference (`nested_structure_needs_subcomposition`, `timeline_track_too_dense`), not an error. A reasonable v2 refactor if this gets iterated on further, not done here given v1 scope.
- Real bug found and fixed during build: root-level scene `<section>` elements did not actually receive automatic 100%-sized absolute layout as expected from the "root-level clips get automatic layout" rule — content was confined to a small top-left box. Fixed by giving `.scene` explicit `position: absolute; inset: 0; width: 100%; height: 100%`, confirmed via snapshot before/after.
- `check` passes clean: 0 errors, 0 runtime warnings, 0 layout findings, 13/13 contrast checks pass.
- Poster frame picked from the settled product-reveal beat (36.5s) and baked into frame 0 via the documented ffmpeg overlay technique — confirmed via frame extraction, duration unchanged (180.000000s).

## What's genuinely verified vs. not
- Verified: `hyperframes check` passes clean; visual snapshot review at 9 timestamps across the full runtime; final render duration confirmed via `ffprobe`; poster bake confirmed via frame extraction.
- Not done in this v1 pass: audio-reactive visuals, beat-sync cue locking (the bundled track's cues weren't pulled and aligned to specific reveals), sub-composition refactor, a full audio mix review by ear (the render completed but wasn't manually listened through end-to-end as part of this automated pass).

# Brag Plan: Parali Setu

## What is this app?
A live matching system that connects farmers holding crop stubble with companies that turn it into packaging, cutlery, and biofuel pellets — in Hindi or Punjabi, by voice or text — so selling it is faster than burning it.

## The angle
This isn't a generic marketplace pitch. The hook is the real, specific, legitimately dramatic stake: Punjab's farmers burn ~15-20 million tonnes of paddy straw every October because nothing faster than fire exists in their 10-15 day sowing window — and that smoke is a direct, named cause of Delhi's worst air days. The video opens on that real stake, not on the product. The product is the answer, delivered as a trailer-scale reveal, then proven with the actual live flow (a real Punjabi voice listing, a real OR-Tools match, a real BigQuery ML forecast) rather than described in marketing copy.

## Hook (first 2-3 seconds)
Full-bleed, no logo yet. A single sweeping line, cinematic hook style:
"EVERY OCTOBER, PUNJAB'S SKY TURNS TO SMOKE."
Warm-to-smoke color treatment on the background (the product's own marigold accent #b8651f, desaturating toward smoke-grey), not literal photography — stays in the product's own visual language.

## Key moments (the middle)
- The real scale stat landing hard: "15-20 MILLION TONNES. BURNED. EVERY SEASON." — then the human reason, not villain-framing: "Not because farmers want to. Because nothing faster exists."
- The actual farmer flow, recreated from the real UI: a Punjabi voice listing resolving into a match card, field by field, in real time.
- The negotiation beat: a price number ticking live from ₹8.68 to ₹9.50 after a one-line counter-offer — the smallest, most convincing proof this is a real system, not a mockup.
- The company side: a real BigQuery ML forecast card landing ("Prioritize disposable plates — target Gujarat. Peak week Oct 29, ~3,967 units") — proof the AI layer does more than chat.
- Three "superpower" claims stated like cinematic capabilities, each true and specific: "Gemini listens. In Hindi. In Punjabi." / "OR-Tools decides every number — Gemini never touches one." / "BigQuery ML sees the season ahead."

## Outro / punchline
Return to the opening sky — now clearing, sun breaking through the smoke-to-warm gradient. One line: "SELLING. NOT BURNING." Then the wordmark, tagline, and the live URL. A long, confident hold — cinematic restraint, not a hard sell.

## User flow worth showing
1. **Entry** — farmer speaks a stubble listing in Punjabi (real transcript, real translation subtitle).
2. **Key action** — Gemini extracts it, the OR-Tools solver matches it live against real company demand; a one-line negotiation re-solves the price live.
3. **Result** — a spoken-language-appropriate match card (buyer, price, pickup date) on the farmer side, and a forecast-driven recommendation card on the company side.

## Tone
- Preset: `cinematic`
- Creative direction: "a grounded climate-tech launch film — the gravity of a real social-impact problem (farmer livelihoods, Delhi's air) treated with trailer-scale seriousness, not startup hype. No jokes at the subject's expense."
- Interpretation: Big type, full-bleed scenes, dramatic wipes/crossfades, 2-3 big SFX hits reserved for genuine turns (product reveal, mid-point proof, outro) rather than scattered everywhere. Pacing stays confident and held, not frantic, even though the runtime (180s) is far longer than this tone's native 15-25s window — scenes are scaled up in duration and count, not sped up.

## Format: landscape — 1920x1080
## Duration: 180s (explicit override of the skill's 15-25s default, per direct request — this is for the hackathon's required ~3-4 minute demo video, not a social hype clip)

## Visual identity (from the project)
- Background: `#fbfaf7` (warm off-white)
- Surface/card: `#ffffff`
- Accent: `#b8651f` (warm terracotta/marigold), soft accent fill `#faeadb`
- Ink/text: `#201c14`, soft ink `#5c5648`
- Display font: Fraunces (serif, weight 500-600)
- Body/mono font: IBM Plex Sans (body), IBM Plex Mono (labels/data — use for all numeric displays, tabular-nums)
- Strongest visual element: the match-card reveal (`match-row` label/value pairs filling in) and the amber `rec-card` recommendation block — both real, working UI, not invented for the video

## Share copy (draft)
"🌾 Parali Setu: an AI-mediated marketplace that pays Punjab's farmers to sell their stubble instead of burning it — live voice in Hindi & Punjabi, a real OR-Tools match, a real BigQuery ML forecast. Built for the Google Cloud AI Builder Cup 2026."

## Audio direction
- Role: cinematic support — a steady bed under the whole arc, with SFX reserved for genuine turning points, not every cut.
- Music: `happy-beats-business-moves-vol-12-by-ende-dot-app.mp3` (1:58/118s — "steady and clean," the bundled track explicitly matched to `polished`/`cinematic`). It's shorter than this video's 180s runtime: loop it once with a ~2-3s crossfade around the 115-118s mark (landing inside the quieter architecture-claims beat, not across a dramatic hit) rather than a hard restart.
- Music treatment: fade in under the hook (0-1.5s), hold low-to-mid through the problem/reveal, lift slightly under the product reveal and the live-flow proof scenes, settle back down for the three capability claims, swell once more into the outro, long fade on the final hold.
- Music cue guidance: unavailable until the track is copied into the composition and analyzed at composition time (`npx hyperframes beats` or `analyze_music_cues.py`, per `audio.md`) — Hyperframes should run that before locking SFX timestamps. Treat any cues as timing bias only; never let a cue override a readability floor.
- Audio-reactive treatment: subtle — the hero sky/gradient in the hook and outro may breathe slightly with RMS; the match-card and rec-card surfaces may gain faint presence on bass. No waveform/equalizer visuals, no strobing.
- SFX posture: 2-3 big cinematic hits (`impact/impactBell_heavy_000` on the product-name reveal, `impact/impactBell_heavy_003` or `_004` on the outro logo), plus a lighter, more frequent layer of matched interaction sound during the actual UI-recreation scenes (card/field reveals, the negotiation price-tick, the forecast card landing) — those are real "simulated interaction" moments and should sound like it, scored from `casino/card-place-*`, `interface/drop_*`, and `interface/click_*` per the moment → sound table, not left silent just because the tone is restrained elsewhere.
- Audio-coupled moments: the Punjabi voice listing typing out as subtitle text (subtle keypress or a soft drop per word, not every character — dense copy, thin out per `audio.md`'s guidance); each match-card field landing one by one; the price number ticking during negotiation; the recommendation card's three sequential rec-card facts.
- Restraint rule: never add sound to cover for a weak visual; never score the smoke/stat scenes with anything upbeat — let that beat stay sober.

## Storyboard

### Scene 1 — The hook — 15s
Full-bleed background shifting from warm marigold toward a smoke-grey haze. One line slams in and holds: "EVERY OCTOBER, PUNJAB'S SKY TURNS TO SMOKE." No logo, no UI yet.
Sequential/interaction: none
Audio intent: sober, tense anticipation — not dramatic stinger yet
Audio-coupled idea: none — let the line hold in near-silence under a very low music fade-in
Music: fade in, low (vol ~0.15) from 0s
Transition mood: dramatic wipe → Scene 2

### Scene 2 — The real scale — 15s
Big type, two beats: "15-20 MILLION TONNES. BURNED. EVERY SEASON." holds, then crossfades to the human reason, smaller and warmer: "Not because farmers want to. Because nothing faster exists." (the real PRD theory-of-change, not a villain story)
Sequential/interaction: two sequential text beats, each held to the reading floor (~2.5s / ~3s)
Audio intent: the stat lands with weight; the human-reason line softens it
Audio-coupled idea: a single low impact under the stat's arrival
Music: still low, slight lift at the stat
Transition mood: soft crossfade → Scene 3

### Scene 3 — Product reveal — 15s
The wordmark slams in full screen on the warm `#fbfaf7` background: "🌾 PARALI SETU" in Fraunces, large. Tagline beneath: "Parali. Stubble. Setu. Bridge. A live match between farmers who have it, and buyers who'll pay for it — before it burns."
Sequential/interaction: wordmark scales in (0.95→1.0), tagline fades up after
Audio intent: the turn — this is the "ta-da," cinematic hero moment
Audio-coupled idea: impact/impactBell_heavy_000 at wordmark entry
Music: lifts to mid energy here and stays through the live-flow scenes
Transition mood: dramatic wipe → Scene 4

### Scene 4 — Farmer flow, part 1 (the listing) — 20s
Recreate the real farmer page: language toggle set to Punjabi, a mic icon pulsing, then a real transcript types out — "ਮੇਰੇ ਕੋਲ 12 ਕੁਇੰਟਲ ਪਰਾਲੀ ਹੈ ਸੰਗਰੂਰ ਵਿੱਚ..." — with a soft English gloss beneath it ("12 quintals of stubble, Sangrur"). Card frame matches the real `.card`/`.transcript` styling.
Sequential/interaction: transcript types out word by word; translation fades up after
Audio intent: intimate, real — a single real voice being heard and understood
Audio-coupled idea: light keypress/typing texture under the transcript (thin, not every character)
Transition mood: clean crossfade → Scene 5 (same scene continues the beat)

### Scene 5 — Farmer flow, part 2 (the match) — 20s
The real match-card fills in field by field, exactly as the product does it: QUANTITY → CROP → BUYER → PRICE → PICKUP BY, each row landing in sequence, then the Hindi/Punjabi explanation line fades in beneath.
Sequential/interaction: 5 match-row fields land one by one, ~0.6-0.8s apart, each held to the reading floor
Audio intent: satisfying, mechanical precision — the system actually works
Audio-coupled idea: `casino/card-place-*` or `interface/drop_001` on each row landing, slightly louder on the final (PRICE) row
Music: steady mid energy
Transition mood: clean cut → Scene 6

### Scene 6 — The negotiation proof — 15s
A single typed line appears: "can we get 9.50 per kg instead?" — then the PRICE value on the match card updates live, ticking from ₹8.68 to ₹9.50.
Sequential/interaction: text types in, then the number ticks up over ~0.8s
Audio intent: the smallest, most convincing proof — "this isn't a mockup"
Audio-coupled idea: `interface/click` on send, a short rising tick sound under the number change
Transition mood: dramatic wipe → Scene 7

### Scene 7 — Company flow (the forecast) — 18s
Cut to the company dashboard: the real `rec-card` slides in — "Prioritize disposable plates — target Gujarat." with the peak-week stat beneath: "Peak demand week Oct 29 — ~3,967 units." Sourced from a real BigQuery ML forecast, said as a one-line caption: "Trained offline on real seasonal demand. Not a guess."
Sequential/interaction: rec-card slides in, then the peak-week stat reveals beneath it
Audio intent: a second, different kind of proof — this time for the business side
Audio-coupled idea: `interface/drop_001` on the card's arrival
Transition mood: clean crossfade → Scene 8

### Scene 8 — Three capability claims — 24s
Cinematic "superpower" beats, one per sub-scene (~8s each), big type over the warm background:
"GEMINI LISTENS. IN HINDI. IN PUNJABI."
"OR-TOOLS DECIDES EVERY NUMBER. GEMINI NEVER TOUCHES ONE."
"BIGQUERY ML SEES THE SEASON AHEAD."
Sequential/interaction: three sequential text slams, each held to its reading floor before the next
Audio intent: confident, declarative — the architecture stated like a feature list that actually means something
Audio-coupled idea: a soft impact under each of the three lines, consistent and restrained
Music: settles back down slightly — this is information, not spectacle
Transition mood: dramatic wipe → Scene 9

### Scene 9 — The turn back, and outro — 38s
Return to the opening sky — now the smoke-to-marigold gradient clears, warm light breaking through. One line: "SELLING. NOT BURNING." Hold. Then the wordmark reappears, smaller, with the tagline and live URL beneath: "parali-setu.web.app" and a small credit line: "Built for the Google Cloud AI Builder Cup, JAPAC 2026."
Sequential/interaction: sky clears (continuous motion, ~4s), line holds (~3s), wordmark/tagline/URL fade in and hold to the end
Audio intent: release, confidence, a clean landing — not a hard sell
Audio-coupled idea: impact/impactBell_heavy_003 or _004 under the wordmark's return
Music: swells once, then a long fade to silence over the final ~6s
Transition mood: long hold → end

**Music mood for this video:** cinematic — steady and clean, restrained builds, no aggressive drops.
**Audio summary:** A single steady bed carries the whole arc from sober opening to confident close, lifting only at the product reveal and the live-flow proof scenes; 2-3 reserved cinematic impact hits mark the real turns (product reveal, outro), while the actual UI-recreation scenes get a lighter, specific layer of interaction sound matched to what's genuinely happening on screen.

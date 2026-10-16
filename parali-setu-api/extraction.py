"""The three Gemini jobs in the farmer/company flow (PRD Section 8.1 /
8.2 / 12): extract a structured listing from natural language, parse a
negotiation counter-offer into a price delta, and explain a match back
in plain language. Every function returns structured data or plain
text -- never a price or quantity Gemini invented itself. solver.py
always produces the actual numbers; these functions only translate
language into solver inputs or solver outputs into language.
"""
from __future__ import annotations

import json
from datetime import date

from google import genai
from google.genai import types

from gemini_client import call_gemini

VALID_CROP_TYPES = ("rice_stubble", "wheat_stubble")
VALID_QUALITY_GRADES = ("dry", "wet", "mixed")
VALID_FIELD_CONDITIONS = ("unburned", "partially_burned", "burned", "inconclusive")


def extract_listing(client: genai.Client, raw_text: str, language: str, today: date | None = None) -> dict | None:
    """PRD 8.1.2 -- turn a farmer's spoken/typed listing into a structured
    record. Returns None if Gemini is unavailable or the response isn't
    valid JSON; callers must show a plain error, never guess a listing.

    `today` anchors relative dates like "by the 25th" -- found live
    (not hypothetical) that without an explicit anchor, Gemini resolved
    a bare day-of-month against the wrong year.
    """
    today = today or date.today()
    prompt = f"""You are extracting a structured crop-residue (stubble) listing
from a farmer's message. The message is in {language}. This message may be a
speech-to-text transcript and can contain recognition errors -- words that
don't quite fit grammatically, or a stray word that doesn't belong. Today's
date is {today.isoformat()}. Respond with ONLY a JSON object, no other text,
matching exactly this shape:

{{
  "quantity_kg": <number, convert quintals to kg by multiplying by 100 if the farmer used quintals>,
  "crop_type": <one of "rice_stubble" or "wheat_stubble">,
  "village_or_district": <string, as stated>,
  "ready_by": <ISO date string YYYY-MM-DD, or null>,
  "contact": <string if a phone number or name was given, else null>
}}

Strict rule for ready_by, since a wrong specific date is worse than none: only
fill it in if the message states an explicit day number (e.g. "the 25th",
"20 October") or an unambiguous relative timeframe (e.g. "next week", "in 5
days") that you can resolve against today's date. If the message only names a
month with no day (e.g. a stray or garbled word near "October" with no
number), or is otherwise vague, return null -- do NOT guess, round to, or
infer any particular day of that month. The same caution applies to every
other field: if a word looks like a transcription error or doesn't clearly
state a value, use null rather than resolving it to a specific guess.

Farmer's message: "{raw_text}"
"""
    text = call_gemini(client, prompt, json_mode=True)
    if text is None:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None

    if parsed.get("crop_type") not in VALID_CROP_TYPES:
        parsed["crop_type"] = None
    return parsed


def read_stubble_quality(client: genai.Client, image_bytes: bytes, mime_type: str = "image/jpeg") -> dict | None:
    """PRD 8.1.3 -- optional multimodal perception signal, never a price
    input. Returns {"quality_grade": "dry"|"wet"|"mixed", "note": str} on
    success, or None if Gemini is unavailable -- callers must fall back
    to quality_grade="unknown" (self-reported crop_type only), never guess
    a grade. This is the one function in this file that takes an image
    instead of text, but the contract is identical: Gemini perceives,
    it never decides a number.
    """
    prompt_part = types.Part.from_text(text="""Look at this photo of harvested crop
residue (stubble) -- this could be cut stalks still standing/lying in the
field after harvest, or residue already gathered into a pile; either is a
valid photo. Respond with ONLY a JSON object:

{
  "quality_grade": <one of "dry", "wet", or "mixed" (visibly mixed with other
    debris/soil) -- your best visual read>,
  "note": <one short phrase explaining the read, e.g. "pale gold, no visible moisture">
}

If the image genuinely isn't crop residue/stubble at all (a different subject
entirely), or the photo is too unclear to make any reasonable call, respond
with {"quality_grade": null, "note": "not a usable photo"} instead of
guessing.
""")
    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

    text = call_gemini(client, [prompt_part, image_part], json_mode=True)
    if text is None:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None

    if parsed.get("quality_grade") not in VALID_QUALITY_GRADES:
        parsed["quality_grade"] = None
    return parsed


def read_no_burn_proof(client: genai.Client, image_bytes: bytes, mime_type: str = "image/jpeg") -> dict | None:
    """Feature 5 -- a farmer's photo evidence that their harvested field
    was NOT burned, same perception-only contract as read_stubble_quality:
    Gemini only reads what the photo shows, it never decides the trust
    score itself (that's solver.score_no_burn_submission's job, combined
    with Part A's real satellite corroboration).
    """
    prompt_part = types.Part.from_text(text="""Look at this photo of a
harvested field, submitted as evidence that crop residue was NOT burned after
harvest (sold instead). Respond with ONLY a JSON object:

{
  "field_condition": <one of "unburned" (clear/bare soil or gathered residue,
    no burn marks), "partially_burned" (some charred patches visible),
    "burned" (clearly and extensively charred/blackened), or "inconclusive">,
  "note": <one short phrase explaining the read>
}

If the image genuinely isn't a field at all, or is too unclear to make any
reasonable call, respond with {"field_condition": "inconclusive", "note":
"not a usable photo"} instead of guessing.
""")
    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

    text = call_gemini(client, [prompt_part, image_part], json_mode=True)
    if text is None:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None

    if parsed.get("field_condition") not in VALID_FIELD_CONDITIONS:
        parsed["field_condition"] = None
    return parsed


def explain_pricing(client: genai.Client, match: dict, context: dict, language: str) -> str | None:
    """Feature 3 -- narrate WHY a match landed at its price, using only
    already-computed numbers (same verbatim-numbers contract as
    explain_match): the quality grade, the urgency/trust multipliers the
    solver actually applied, and the forecast if one exists. No distance
    field exists in this codebase (no geocoding anywhere) -- deliberately
    omitted rather than invented, a correction from the original research
    brief's assumption that one would be available.
    """
    multiplier_notes = []
    if context.get("urgency_multiplier_applied", 1.0) > 1.0:
        multiplier_notes.append(
            f"the listing's pickup deadline made it {context['urgency_multiplier_applied']:.2f}x more "
            "likely to be prioritized in matching"
        )
    if context.get("trust_score") is not None:
        multiplier_notes.append(f"the farmer's trust score is {context['trust_score']:.2f} (of 1.0)")
    if context.get("forecast_summary"):
        multiplier_notes.append(context["forecast_summary"])

    prompt = f"""Write a short, plain-language explanation in {language} (2-3
sentences) of why this crop-residue match landed at its price. Use exactly
these facts, do not change or round any numbers, and do not invent any
factor not listed here:
- Quality grade: {context.get('quality_grade', 'unknown')}
- Price agreed: {match.get('price_agreed_per_kg')} rupees per kg
- Quantity matched: {match.get('matched_kg')} kg
{"- Other real factors behind this match: " + "; ".join(multiplier_notes) if multiplier_notes else "- No other factors applied beyond the standing price offer."}

Plain prose only, no markdown formatting, no asterisks.
"""
    return call_gemini(client, prompt, json_mode=False)


def cross_check_voice_and_photo(
    client: genai.Client, transcript: str, quality_grade: str | None, quality_note: str | None, language: str
) -> dict | None:
    """Feature 4 -- flags an explicit contradiction between what a farmer
    said and what their photo showed (e.g. transcript claims "dry" while
    the photo read came back "wet"). Informational only in this pass --
    does not feed the solver or the trust score; a stretch goal to wire
    it into Feature 5's scoring is deliberately not bundled here. Flags
    only explicit contradictions, never infers fraud from silence or an
    unclear photo read.
    """
    if not quality_grade or quality_grade == "unknown":
        return {"mismatch_detected": False, "note": "no photo quality read to cross-check against"}

    prompt = f"""A farmer's spoken listing (in {language}) was transcribed as:
"{transcript}"

A separate photo of the same stubble was independently read as quality grade
"{quality_grade}" (note: {quality_note or "none"}). Respond with ONLY a JSON
object:

{{
  "mismatch_detected": <true ONLY if the transcript explicitly states a
    quality/condition that directly contradicts "{quality_grade}" (e.g. the
    farmer says "sukhi" (dry) but the photo read is "wet") -- false if the
    transcript says nothing about quality at all, or is ambiguous>,
  "note": <one short phrase explaining the finding, or null if no mismatch>
}}
"""
    text = call_gemini(client, prompt, json_mode=True)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def parse_custom_constraint(client: genai.Client, raw_text: str, language: str) -> dict | None:
    """Part D -- a company states a custom sourcing rule in plain language
    ("at least 60% of what I buy should be dry"), Gemini classifies it
    into one closed, bounded template the solver can actually enforce as
    a real LP term (solver.py's `_add_custom_constraint_terms`). Same
    bounded-extraction contract as extract_listing: a human-stated value,
    parsed, never invented -- the only thing different from every other
    function in this file is where the parsed value lands afterward
    (inside the optimization model's structure, not just a listing/match
    attribute).

    Only one constraint type exists in this build (`quality_ratio_min`) --
    an earlier `single_farmer_cap_pct` design was cut after five rounds of
    judge-eval kept finding new errors specific to its self-referential
    shape (`x <= cap*T` where `T` includes `x` itself); `quality_ratio_min`
    doesn't share that shape.

    Returns {"constraint_type": "quality_ratio_min", "quality_grade": ...,
    "threshold": <float, clamped to [0.0, 1.0]>} on a recognized request,
    or {"constraint_type": None} for anything else -- rejected, not
    improvised into a new template, same enum-rejection discipline as
    read_stubble_quality/extract_listing. The clamp is a plain sanity
    bound here, not a math-safety one: solver.py's constraint is anchored
    to the demand's fixed `quantity_needed_kg`, not a ratio denominator
    that could divide by zero, so there's no blow-up risk at threshold=1.0
    the way an earlier, reverted formulation had.
    """
    prompt = f"""A company states a custom sourcing rule for crop-residue
purchases, in {language}:
"{raw_text}"

Respond with ONLY a JSON object:

{{
  "constraint_type": <"quality_ratio_min" if the message states a minimum
    fraction/percentage of purchases that should be a specific quality
    grade (e.g. "at least 60% dry", "mostly dry, say 70%"), else null for
    anything else (a price request, a farmer cap, a delivery timeline, or
    anything this template doesn't cover -- do NOT invent a new type)>,
  "quality_grade": <one of "dry", "wet", "mixed" if constraint_type is
    "quality_ratio_min", else null>,
  "threshold": <float between 0 and 1 (convert a stated percentage by
    dividing by 100) if constraint_type is "quality_ratio_min", else null>
}}
"""
    text = call_gemini(client, prompt, json_mode=True)
    if text is None:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None

    if parsed.get("constraint_type") != "quality_ratio_min":
        return {"constraint_type": None}
    if parsed.get("quality_grade") not in VALID_QUALITY_GRADES or parsed.get("threshold") is None:
        return {"constraint_type": None}

    threshold = max(0.0, min(float(parsed["threshold"]), 1.0))
    return {
        "constraint_type": "quality_ratio_min",
        "quality_grade": parsed["quality_grade"],
        "threshold": threshold,
    }


def parse_negotiation_price(client: genai.Client, raw_text: str, current_price_per_kg: float) -> dict | None:
    """PRD 8.1.7 / 8.2.3 -- turn a counter-offer like "I need at least
    9.50 a kilo" into a structured price delta. Only ever returns a
    *requested* price for the solver to re-run against -- this function
    never decides whether the request is accepted; apply_negotiation()
    in solver.py re-solves and the result is the actual answer.
    """
    prompt = f"""A party in a crop-residue sale negotiation sent this message:
"{raw_text}"

The current agreed price is {current_price_per_kg} rupees per kg. Respond with
ONLY a JSON object:

{{
  "requested_price_per_kg": <number if the message requests a specific new
    price per kg (convert per-quintal to per-kg by dividing by 100 if
    needed), else null if no specific price was requested>,
  "is_price_request": <true or false -- false if the message is about
    something else (e.g. pickup timing) that this system doesn't yet
    parse into a structured delta>
}}
"""
    text = call_gemini(client, prompt, json_mode=True)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def narrate_negotiation_turn(
    client: genai.Client, persona: str, proposed_price_per_kg: float, context: dict, language: str
) -> str | None:
    """Feature 2 -- one short, grounded sentence in the voice of
    `persona` ("farmer" or "buyer") proposing `proposed_price_per_kg` as
    the next offer. `context["reason"]` must be a real fact about THIS
    negotiation (the listing's real urgency multiplier and why), not
    generic negotiating language -- the output never contains a number
    Gemini invented, only the one already decided by
    solver.negotiation_concession_schedule.
    """
    prompt = f"""Write exactly ONE short sentence in {language}, in the voice
of the {persona} side of a crop-residue price negotiation, proposing
{proposed_price_per_kg} rupees per kg as the next offer. Ground the tone in
this real fact about the situation, do not invent any other reason:
{context.get('reason', 'an ongoing negotiation')}.

Do not state any number other than {proposed_price_per_kg}. Plain prose only,
no markdown formatting, no asterisks.
"""
    return call_gemini(client, prompt, json_mode=False)


def explain_match(client: genai.Client, match: dict, language: str) -> str | None:
    """PRD 8.1.6 -- narrate the solver's result in the farmer's language.
    Takes already-computed numbers (matched_kg, price_agreed_per_kg,
    company name) and only ever repeats them in prose; never recomputes
    or adjusts them.
    """
    prompt = f"""Write a short, warm message in {language} (2-3 sentences) telling
a farmer the result of their crop-residue stubble listing. Use exactly these
facts, do not change or round any numbers:
- Buyer: {match.get('company_name')}
- Quantity matched: {match.get('matched_kg')} kg
- Price: {match.get('price_agreed_per_kg')} rupees per kg
- Pickup window: {match.get('pickup_window', 'to be confirmed')}

Plain prose only, no markdown formatting, no asterisks.
"""
    return call_gemini(client, prompt, json_mode=False)

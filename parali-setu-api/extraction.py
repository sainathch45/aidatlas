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

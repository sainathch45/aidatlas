"""Mocked tests for extraction.py's three Gemini jobs -- fast, no real
API calls. These were each also live-verified once by hand against the
real Vertex AI endpoint (extract_listing's date-anchoring and the
Punjabi narration were both fixed after that live check caught real
bugs a mock never would have) -- see PRD docs/PARALI_SETU_PRD.md
Section 13 for why a live check still matters even with these in place.
"""
import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extraction import explain_match, extract_listing, parse_negotiation_price  # noqa: E402


def make_fake_client(response_text):
    client = MagicMock()
    client.models.generate_content.return_value = MagicMock(text=response_text)
    return client


def test_extract_listing_parses_valid_json():
    client = make_fake_client(json.dumps({
        "quantity_kg": 800, "crop_type": "rice_stubble",
        "village_or_district": "Sangrur", "ready_by": "2026-10-25", "contact": None,
    }))
    result = extract_listing(client, "8 quintal rice stubble in Sangrur", "Hindi", today=date(2026, 10, 14))
    assert result["quantity_kg"] == 800
    assert result["crop_type"] == "rice_stubble"


def test_extract_listing_rejects_invalid_crop_type_rather_than_trust_it():
    client = make_fake_client(json.dumps({
        "quantity_kg": 800, "crop_type": "cotton_stubble",  # not a valid type
        "village_or_district": "Sangrur", "ready_by": None, "contact": None,
    }))
    result = extract_listing(client, "...", "Hindi", today=date(2026, 10, 14))
    assert result["crop_type"] is None


def test_extract_listing_returns_none_on_gemini_unavailable():
    client = MagicMock()
    client.models.generate_content.side_effect = Exception("unreachable")
    try:
        extract_listing(client, "...", "Hindi", today=date(2026, 10, 14))
        assert False, "expected the underlying exception to propagate from call_gemini"
    except Exception:
        pass


def test_extract_listing_returns_none_on_malformed_json():
    client = make_fake_client("not valid json")
    result = extract_listing(client, "...", "Hindi", today=date(2026, 10, 14))
    assert result is None


def test_parse_negotiation_price_extracts_requested_price():
    client = make_fake_client(json.dumps({"requested_price_per_kg": 9.5, "is_price_request": True}))
    result = parse_negotiation_price(client, "Can we get 9.50 per kg instead?", current_price_per_kg=8.0)
    assert result["requested_price_per_kg"] == 9.5
    assert result["is_price_request"] is True


def test_parse_negotiation_price_non_price_message():
    client = make_fake_client(json.dumps({"requested_price_per_kg": None, "is_price_request": False}))
    result = parse_negotiation_price(client, "Can you pick up on Thursday instead?", current_price_per_kg=8.0)
    assert result["is_price_request"] is False


def test_explain_match_never_asked_to_change_the_numbers():
    """The prompt itself instructs Gemini not to alter the figures --
    this test just confirms the exact match figures are passed through
    into the prompt text unmodified, which is the one thing we can
    actually assert without a live call."""
    client = make_fake_client("plain narration text")
    match = {"company_name": "Co_Pellets_Punjab", "matched_kg": 800,
             "price_agreed_per_kg": 8.5, "pickup_window": "2026-10-26"}
    result = explain_match(client, match, "Punjabi")
    assert result == "plain narration text"
    prompt_sent = client.models.generate_content.call_args.kwargs["contents"]
    assert "800" in prompt_sent
    assert "8.5" in prompt_sent
    assert "Co_Pellets_Punjab" in prompt_sent

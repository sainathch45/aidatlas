"""Tests for call_gemini's retry/fallback behavior -- the two failure
modes here (transient 503, and the free tier's 20/day quota) were both
hit live while building this, not hypothetical edge cases. Uses a fake
client, no real API calls or credentials needed.
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402
from google.genai import errors as genai_errors  # noqa: E402


def make_fake_client(side_effects):
    client = MagicMock()
    client.models.generate_content.side_effect = side_effects
    return client


def test_successful_call_returns_text_on_first_try():
    main.QUOTA_EXHAUSTED = False
    ok_response = MagicMock(text='{"a": "b"}')
    client = make_fake_client([ok_response])
    result = main.call_gemini(client, "prompt", json_mode=True)
    assert result == '{"a": "b"}'
    assert client.models.generate_content.call_count == 1


def test_transient_503_retries_then_succeeds():
    main.QUOTA_EXHAUSTED = False
    server_error = genai_errors.ServerError(503, {"error": {"message": "overloaded"}})
    ok_response = MagicMock(text="ready")
    client = make_fake_client([server_error, ok_response])
    with patch.object(time, "sleep"):  # don't actually wait in the test suite
        result = main.call_gemini(client, "prompt", json_mode=False)
    assert result == "ready"
    assert client.models.generate_content.call_count == 2


def test_persistent_503_exhausts_retries_and_returns_none():
    main.QUOTA_EXHAUSTED = False
    server_error = genai_errors.ServerError(503, {"error": {"message": "overloaded"}})
    client = make_fake_client([server_error, server_error, server_error])
    with patch.object(time, "sleep"):
        result = main.call_gemini(client, "prompt", json_mode=False)
    assert result is None
    assert client.models.generate_content.call_count == 3


def test_429_quota_exhaustion_fails_fast_no_wasted_retries():
    main.QUOTA_EXHAUSTED = False
    quota_error = genai_errors.ClientError(429, {"error": {"message": "quota exceeded"}})
    client = make_fake_client([quota_error])
    result = main.call_gemini(client, "prompt", json_mode=False)
    assert result is None
    # Exactly one call -- a 429 doesn't get retried, since the quota
    # reset is hours away, not something a few seconds of backoff fixes.
    assert client.models.generate_content.call_count == 1


def test_quota_exhausted_flag_short_circuits_later_calls():
    main.QUOTA_EXHAUSTED = True
    client = make_fake_client([MagicMock(text="should never be reached")])
    result = main.call_gemini(client, "prompt", json_mode=False)
    assert result is None
    assert client.models.generate_content.call_count == 0
    main.QUOTA_EXHAUSTED = False  # reset for other tests


def test_ask_falls_back_gracefully_when_gemini_unavailable():
    """/ask must return real BigQuery/Firestore-backed numbers, not a
    bare 500, when Gemini is exhausted mid-demo."""
    main.QUOTA_EXHAUSTED = True
    fake_docs = [
        MagicMock(
            to_dict=lambda: {
                "admin2_name": "At Tall",
                "admin1_name": "Rural Damascus",
                "admin2_code": "SY0304",
                "quantity_allocated": 133639548.83,
                "idp_population": 364408,
                "active_org_count": 21,
                "need_score": 16564.0,
            }
        )
    ]
    fake_fs = MagicMock()
    fake_fs.collection.return_value.where.return_value.order_by.return_value.limit.return_value.stream.return_value = fake_docs

    with patch.object(main, "get_firestore_client", return_value=fake_fs), patch.object(
        main, "get_gemini_client", return_value=MagicMock()
    ):
        result = main.ask(main.AskRequest(question="why At Tall?", resource_type="shelter"))

    assert result["districts_considered"] == 1
    assert "At Tall" in result["answer"]
    assert "$133,639,549" in result["answer"]
    main.QUOTA_EXHAUSTED = False

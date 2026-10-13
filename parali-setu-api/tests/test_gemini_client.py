"""Tests for call_gemini's retry/fallback behavior -- deliberately the
same cases aidatlas-api/tests/test_gemini_fallback.py covers, since this
is the same proven wrapper reused verbatim for a second project in the
same GCP project. Fake client, no real API calls or credentials needed.
"""
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gemini_client  # noqa: E402
from google.genai import errors as genai_errors  # noqa: E402


def make_fake_client(side_effects):
    client = MagicMock()
    client.models.generate_content.side_effect = side_effects
    return client


def test_successful_call_returns_text_on_first_try():
    gemini_client.QUOTA_EXHAUSTED = False
    ok_response = MagicMock(text='{"a": "b"}')
    client = make_fake_client([ok_response])
    result = gemini_client.call_gemini(client, "prompt", json_mode=True)
    assert result == '{"a": "b"}'
    assert client.models.generate_content.call_count == 1


def test_transient_503_retries_then_succeeds():
    gemini_client.QUOTA_EXHAUSTED = False
    server_error = genai_errors.ServerError(503, {"error": {"message": "overloaded"}})
    ok_response = MagicMock(text="ready")
    client = make_fake_client([server_error, ok_response])
    with patch.object(time, "sleep"):
        result = gemini_client.call_gemini(client, "prompt", json_mode=False)
    assert result == "ready"
    assert client.models.generate_content.call_count == 2


def test_persistent_503_exhausts_retries_and_returns_none():
    gemini_client.QUOTA_EXHAUSTED = False
    server_error = genai_errors.ServerError(503, {"error": {"message": "overloaded"}})
    client = make_fake_client([server_error, server_error, server_error])
    with patch.object(time, "sleep"):
        result = gemini_client.call_gemini(client, "prompt", json_mode=False)
    assert result is None
    assert client.models.generate_content.call_count == 3


def test_429_quota_exhaustion_fails_fast_no_wasted_retries():
    gemini_client.QUOTA_EXHAUSTED = False
    quota_error = genai_errors.ClientError(429, {"error": {"message": "quota exceeded"}})
    client = make_fake_client([quota_error])
    result = gemini_client.call_gemini(client, "prompt", json_mode=False)
    assert result is None
    assert client.models.generate_content.call_count == 1
    gemini_client.QUOTA_EXHAUSTED = False


def test_quota_exhausted_flag_short_circuits_later_calls():
    gemini_client.QUOTA_EXHAUSTED = True
    client = make_fake_client([MagicMock(text="should never be reached")])
    result = gemini_client.call_gemini(client, "prompt", json_mode=False)
    assert result is None
    assert client.models.generate_content.call_count == 0
    gemini_client.QUOTA_EXHAUSTED = False


def test_non_429_client_error_is_not_silently_swallowed():
    """A 400 (e.g. malformed request) must surface, not look identical to
    a clean 'Gemini unavailable' -- swallowing it would hide a real bug."""
    gemini_client.QUOTA_EXHAUSTED = False
    bad_request = genai_errors.ClientError(400, {"error": {"message": "bad request"}})
    client = make_fake_client([bad_request])
    try:
        gemini_client.call_gemini(client, "prompt", json_mode=False)
        assert False, "expected ClientError to propagate"
    except genai_errors.ClientError as exc:
        assert exc.code == 400

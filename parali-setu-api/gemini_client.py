"""Shared Gemini client + retry wrapper for Parali Setu.

Deliberately mirrors aidatlas-api/main.py's proven get_gemini_client() /
call_gemini() pattern verbatim -- same project, same already-solved
gotchas (Developer API's 20/day cap, gemini-2.5-flash deprecation,
region-specific endpoints 404ing), no reason to rediscover any of them.

Every function here does language in, language or JSON-shaped-text out.
None of them touch a price or a quantity decision -- that's solver.py's
job, always (PRD docs/PARALI_SETU_PRD.md, Section 9 / 13).
"""
from __future__ import annotations

import os
import time

from google import genai
from google.genai import errors as genai_errors

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "ai-builder-cup-aidatlas")
VERTEX_LOCATION = os.environ.get("AGENT_PLATFORM_LOCATION", "global")

QUOTA_EXHAUSTED = False


def get_gemini_client() -> genai.Client:
    return genai.Client(vertexai=True, project=PROJECT_ID, location=VERTEX_LOCATION)


def call_gemini(client: genai.Client, prompt: str, json_mode: bool = False) -> str | None:
    """Three retries on transient server errors, then gives up and returns
    None -- callers must handle None explicitly (show a plain error, never
    fabricate a result). PRD Section 13: 'if a Gemini call fails, show a
    plain error -- never let the model guess a price or quantity.'

    Mirrors aidatlas-api/main.py's call_gemini exactly, including the
    QUOTA_EXHAUSTED short-circuit -- once a 429 is seen, every later call
    skips straight to None with zero wasted retries/API calls, rather than
    re-discovering the same quota exhaustion three times per request.
    """
    global QUOTA_EXHAUSTED
    if QUOTA_EXHAUSTED:
        return None

    config = {"response_mime_type": "application/json"} if json_mode else {}

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL, contents=prompt, config=config
            )
            return response.text
        except genai_errors.ServerError:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
            continue
        except genai_errors.ClientError as exc:
            if exc.code == 429:
                QUOTA_EXHAUSTED = True
                return None
            raise

    return None

"""Crisis Resource Allocator backend.

Deploys to Cloud Run. Calls the free-tier Gemini Developer API directly
(no Vertex/Agent Platform needed), reads/writes Firestore for the
coordinator dashboard, and will eventually read the allocation model's
output from BigQuery (see bigquery/schema.sql).

Local run:
    pip install -r requirements.txt
    GEMINI_API_KEY=... uvicorn main:app --reload --port 8080
"""

import os

from fastapi import FastAPI, HTTPException
from google import genai
from pydantic import BaseModel

app = FastAPI(title="Crisis Resource Allocator")

# Confirmed available on the Gemini free tier as of Oct 2026 research; if
# AI Studio's model picker shows a newer default (e.g. a Gemini 3 Flash
# variant) when you get your key, swap this.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def get_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY not set")
    return genai.Client(api_key=api_key)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/gemini-ping")
def gemini_ping():
    """Smoke-test the free-tier Gemini key end to end."""
    client = get_client()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents="Reply with the single word: ready",
    )
    return {"model": GEMINI_MODEL, "reply": response.text}


class AllocationRequest(BaseModel):
    crisis_region: str
    resource_type: str  # 'food' | 'medicine' | 'shelter'


@app.post("/allocate")
def allocate(req: AllocationRequest):
    """Stub. Real version: pull need/supply from BigQuery, run the
    greedy/LP allocation model, then ask Gemini to narrate the rationale
    for each row. Wiring this up is blocked on picking a region and
    inspecting its real HAPI export (see data/README.md), not on any
    infra limitation.
    """
    raise HTTPException(status_code=501, detail="Allocation model not wired up yet")

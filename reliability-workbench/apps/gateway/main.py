"""
Reliability Workbench Gateway — single FastAPI service exposing all 3 tasks.

Why one gateway: William's decision (TALK_v2.md §C). One Zeabur service, three routes.
Code structure remains decoupled (packages/ + apps/), only deployment is monolithic.

Endpoints:
  POST /sec10k/extract       Task 3 — 10-K item-level extraction
  POST /browser/run          Task 2 — natural-language browser task (placeholder)
  POST /cicd/run-skill       Task 1 — CI/CD skills (placeholder)

  GET  /skills               list all registered skills
  POST /skills/{name}        invoke any skill by name (used by demo)
  GET  /traces/{trace_id}    replay a trace
  GET  /healthz              liveness
  GET  /ready                readiness (verifies skill registry loads)
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from packages.skills_registry import (
    SkillsRegistry, SkillNotFoundError, SkillExecutionError, SchemaError
)
from packages.observability import replay
from packages.cost_ledger import CostLedger


# ───────────────────────────────────────────────────────────────────
# Initialization
# ───────────────────────────────────────────────────────────────────
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
CACHE_DIR = REPO_ROOT / "_cache"
CACHE_DIR.mkdir(exist_ok=True)

registry = SkillsRegistry(skills_dir=str(SKILLS_DIR))
ledger = CostLedger(db_path=str(CACHE_DIR / "ledger.db"))

app = FastAPI(
    title="Reliability Workbench",
    description="Unified service for 3 AI Coding Test tasks",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# ───────────────────────────────────────────────────────────────────
# Schemas (input shapes)
# ───────────────────────────────────────────────────────────────────
class Sec10kRequest(BaseModel):
    cik: str | None = Field(None, description="10-digit zero-padded CIK")
    accession: str | None = Field(None, description="Accession number with dashes")
    file_url: str | None = Field(None, description="Alternative: direct URL")
    always_run_llm: bool = False
    resolve_incorporation: bool = True
    max_chars_to_llm: int = 80000
    model_preference: str = "auto"


class BrowserRequest(BaseModel):
    task: str = Field(..., description="Natural-language browser task")
    site_hint: str | None = None
    max_steps: int = 15


class CicdRequest(BaseModel):
    skill: str = Field(..., description="Which CI skill to invoke (lint-and-test, etc.)")
    repo_url: str
    ref: str = "main"
    extra_inputs: dict = {}


class SkillInvokeRequest(BaseModel):
    inputs: dict = Field(default_factory=dict)


# ───────────────────────────────────────────────────────────────────
# Routes
# ───────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "service": "Reliability Workbench",
        "version": app.version,
        "endpoints": {
            "sec10k": "POST /sec10k/extract",
            "browser": "POST /browser/run (not yet implemented)",
            "cicd": "POST /cicd/run-skill (not yet implemented)",
            "skills": "GET /skills",
            "skill_invoke": "POST /skills/{name}",
            "trace": "GET /traces/{trace_id}",
            "health": "GET /healthz",
            "ready": "GET /ready",
        },
    }


@app.get("/healthz")
def healthz():
    return {"status": "ok", "ts": time.time()}


@app.get("/ready")
def ready():
    """Verify skill registry loads + at least the Task 3 chain is present."""
    skills = [s.name for s in registry.list_all()]
    required = {"10k-fetch", "10k-find-items", "10k-confirm-items-llm",
                "10k-resolve-incorporation", "10k-extract-structured"}
    missing = required - set(skills)
    return {
        "status": "ready" if not missing else "degraded",
        "skills_loaded": len(skills),
        "skills": skills,
        "missing_required": sorted(missing),
    }


@app.get("/skills")
def list_skills():
    return [
        {"name": s.name, "description": s.description}
        for s in registry.list_all()
    ]


@app.post("/skills/{name}")
def invoke_skill(name: str, req: SkillInvokeRequest):
    try:
        result = registry.execute(name, req.inputs)
        return {
            "skill": name,
            "validated": result.validated,
            "output": result.output,
            "warnings": result.warnings,
            "schema_violations": result.schema_violations,
            "duration_ms": result.duration_ms,
        }
    except SkillNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except SchemaError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except SkillExecutionError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/sec10k/extract")
def sec10k_extract(req: Sec10kRequest):
    """Task 3: end-to-end 10-K extraction."""
    if not req.file_url and not (req.cik and req.accession):
        raise HTTPException(
            status_code=422,
            detail="must provide either file_url OR (cik + accession)",
        )
    inputs = req.model_dump(exclude_none=True)
    try:
        result = registry.execute("10k-extract-structured", inputs)
    except SchemaError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except SkillExecutionError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result.output


@app.post("/browser/run")
def browser_run(req: BrowserRequest):
    """Task 2: not yet implemented."""
    raise HTTPException(
        status_code=501,
        detail="browser-agent not yet implemented; Task 2 in progress",
    )


@app.post("/cicd/run-skill")
def cicd_run(req: CicdRequest):
    """Task 1: not yet implemented."""
    raise HTTPException(
        status_code=501,
        detail="cicd-skills not yet implemented; Task 1 in progress",
    )


@app.get("/traces/{trace_id}")
def get_trace(trace_id: str):
    try:
        events = replay(trace_id)
        return {"trace_id": trace_id, "events": events, "step_count": len(events)}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"trace {trace_id} not found")


@app.get("/cost/summary")
def cost_summary(group_by: str = "task", since_hours: float | None = None):
    """Aggregate cost from ledger."""
    since_unix = (time.time() - since_hours * 3600) if since_hours else None
    return {
        "group_by": group_by,
        "since_unix": since_unix,
        "total_spent_usd": ledger.total_spent(since_unix=since_unix),
        "summary": ledger.summary(group_by=group_by, since_unix=since_unix),
    }


# ───────────────────────────────────────────────────────────────────
# Local dev entry
# ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)

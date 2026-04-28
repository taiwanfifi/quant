"""service_base implementation."""
from __future__ import annotations

import time
from typing import Any, Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


class StandardError(BaseModel):
    """Consistent error shape across all services."""
    error_type: str
    message: str
    retryable: bool = False
    trace_id: str | None = None
    hint: str | None = None


def create_app(
    *,
    title: str,
    version: str = "0.1.0",
    cors_origins: list[str] | None = None,
    cost_ledger: Any = None,
    readiness_check: Callable[[], dict] | None = None,
) -> FastAPI:
    """Build a FastAPI app with /healthz, /ready, and CORS."""
    app = FastAPI(title=title, version=version)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["*"],
        allow_methods=["*"], allow_headers=["*"],
    )
    if cost_ledger is not None:
        app.state.cost_ledger = cost_ledger

    @app.get("/healthz")
    def _health():
        return {"status": "ok", "ts": time.time(), "version": version}

    @app.get("/ready")
    def _ready():
        if readiness_check is None:
            return {"status": "ready"}
        try:
            extra = readiness_check() or {}
        except Exception as e:
            return {"status": "degraded", "error": str(e)}
        status = "ready" if extra.get("ok", True) else "degraded"
        return {"status": status, **extra}

    return app

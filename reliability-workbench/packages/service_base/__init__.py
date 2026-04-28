"""
Service Base — minimal FastAPI scaffolding shared across deployable services.

WHAT I DO:
  - create_app(): produces a FastAPI app with /healthz, /ready, error handlers
  - StandardError pydantic model for consistent error responses
  - cost-aware route decorator (binds CostLedger to request.state)

WHAT I DON'T DO:
  - I don't define routes (caller does)
  - I don't run uvicorn (caller does)
  - I don't manage auth (out of scope for portfolio)

IO CONTRACT:
  create_app(title, version="0.1.0", cost_ledger=None) → FastAPI

  StandardError(error_type, message, retryable, trace_id?, hint?)

HIDDEN FACTS:
  - /healthz returns {"status":"ok","ts":...}
  - /ready calls a caller-supplied readiness function (or default no-op = always ready)
  - CORS is wide-open by default; caller can swap

DECOUPLING:
  - Optional dep on packages/cost_ledger
  - No imports from apps/*
"""

from .base import create_app, StandardError

__all__ = ["create_app", "StandardError"]

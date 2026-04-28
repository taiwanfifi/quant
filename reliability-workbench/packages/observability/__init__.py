"""
Observability — trace recorder for replay/debug.

WHAT I DO:
  - Open a TraceContext per task run; emit step events; close with output + outcome
  - Write to JSONL (one trace per file in _traces/<trace_id>.jsonl)
  - Provide replay() to re-read

WHAT I DON'T DO:
  - I don't render dashboards (that's the apps/dashboard service)
  - I don't aggregate (that's cost_ledger / eval_kit)

IO CONTRACT:
  start(task: str) → TraceContext
  step(ctx, kind: str, data: dict) → None  (kind = "rules" | "llm" | "fetch" | "validate" | ...)
  end(ctx, output: dict, success: bool) → trace_id

HIDDEN FACTS:
  - trace_id format: tr_<task>_<timestamp_hex>_<random>
  - Each step is one JSON line (jsonl); appended atomically with O_APPEND
  - When _traces/ doesn't exist, it's created (no failure)
"""

from .trace import start, step, end, replay, TraceContext

__all__ = ["start", "step", "end", "replay", "TraceContext"]

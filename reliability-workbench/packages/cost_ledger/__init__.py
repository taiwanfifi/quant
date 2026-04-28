"""
Cost Ledger — SQLite-backed per-call cost & latency record.

WHAT I DO:
  - Record every LLM call (model, tokens, cost, latency, success, trace_id)
  - Aggregate queries: spend by day, by task, by model
  - Enforce budgets (raise if cumulative spend > cap)

WHAT I DON'T DO:
  - I don't price models myself — caller passes cost_usd already calculated
  - I don't know what "task" means — caller decides namespace ("sec10k", "browser-task-7")

IO CONTRACT:
  record(task, model, tokens_in, tokens_out, cost_usd, latency_ms, success, trace_id)
  summary(since=None, group_by="task" | "model" | "day") → dict
  enforce_budget(task, budget_usd) → raises BudgetExhausted

HIDDEN FACTS:
  - One SQLite file shared across the platform: `_cache/cost_ledger.db`
  - Schema versioned via PRAGMA user_version; migrations in `_migrate()`
  - Concurrent writes: SQLite handles via WAL; we set timeout=30s
"""

from .ledger import CostLedger, BudgetExhausted

__all__ = ["CostLedger", "BudgetExhausted"]

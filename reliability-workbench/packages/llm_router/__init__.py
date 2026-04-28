"""
LLM Router — unified entry point for all LLM calls across the platform.

WHAT I DO:
  - Route a single `call()` to the right provider (Claude / Gemini-via-cookies / Ollama / OpenRouter)
  - Track cost per call (delegated to cost_ledger)
  - Enforce per-task budget caps
  - Provide cascading fallback: rules → cheap model → expensive model → needs_review
  - Cache prompts by (prompt_id, content_hash) when prompt_registry is wired up

WHAT I DON'T DO:
  - I don't know about your task domain (10-K / browser / CI). I just take messages and return text.
  - I don't decide which model is "best" for your task — caller passes hints (`complexity`, `require_local`).
  - I don't validate output schemas — that's the caller's job.

IO CONTRACT:
  Input:  `messages: list[{"role": str, "content": str}]`
          + kwargs: model, prompt_id, budget_usd, require_local, temperature, hint_from_rules
  Output: `LLMResponse(text, model_used, tokens_in, tokens_out, cost_usd, latency_ms,
                       cache_hit, confidence_hint, raw)`

HIDDEN FACTS:
  - Gemini cookies expire silently (~1-2 months). When provider raises CookieExpired,
    I auto-fallback to Claude and emit a warning trace.
  - Anthropic prompt caching has 5-min TTL — if the same prompt_id is called within 5 min,
    cache_hit=True and cost drops dramatically. Caller doesn't need to track this.
  - "auto" model routes by `complexity` hint: easy→haiku, medium→sonnet, hard→opus,
    require_local→ollama.

DECOUPLING:
  Each provider lives in `providers/<name>.py`. They never import each other.
  If gemini_cookies fails to import (e.g., curl_cffi missing), only that provider is unavailable
  — the rest of the router still works.
"""

from .router import LLMRouter, LLMResponse, Message, RouterError, BudgetExhausted, NeedsReview
from .budget import TaskBudget, KillSwitchTriggered

__all__ = [
    "LLMRouter", "LLMResponse", "Message",
    "RouterError", "BudgetExhausted", "NeedsReview",
    "TaskBudget", "KillSwitchTriggered",
]

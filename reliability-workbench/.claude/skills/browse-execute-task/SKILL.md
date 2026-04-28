---
name: browse-execute-task
description: Execute a natural-language browser task (search, fill form, extract data, navigate workflow) using browser-use as the underlying engine, with our verification + drift-report wrapper. Returns the execution result, steps taken, recoveries, and a drift_report.json if any selector required fallback. Use when user gives a browser task in natural language ("find cheapest flight", "buy 1 share", "extract all reviews"), or when an interactive web workflow is required.
---

# Browse Execute Task — Entry Point

The single entry point for Task 2. Wraps `browser-use` (90k stars, DOM-first agent) with:

1. **Verification layer** — every step's post-condition checked before proceeding
2. **5-tier locator cascade** — CSS → XPath → ARIA → text → vision (provided by browser-use's Controller; we add fallback logging)
3. **Drift report** — when fallback strategy succeeds where primary failed, write a structured `drift_report.json` for engineer review (NOT auto-patching the SKILL — Gemini critique caution)
4. **Cost + trace** — every action logged to `_traces/` JSONL; LLM calls to `cost_ledger`

## Architecture (Hybrid per Gemini Round 1)

```
NL task ──► [task-planner internal]
              ↓
         [browser-use Agent: Plan + Act]
              ↓
         [our Verify layer: post-condition check]
              ↓
       success?  ─yes─►  next step
              │ no
              ▼
         [Recover cascade]
              ↓
       drift_report.json (if fallback succeeded)
              ↓
         continue or escalate
```

## When to use

- "Find me the cheapest one-way flight from TPE to NRT on May 5"
- "Buy 1 share of AAPL on this broker site"
- "Extract all 5-star reviews from this product page"
- "Submit this contact form with my info"
- ANY natural-language web workflow

## Inputs

```json
{
  "task": "Find the price of NVDA on Yahoo Finance",
  "site_hint": "https://finance.yahoo.com",     // optional
  "max_steps": 20,                                // hard cap
  "max_runtime_s": 240,
  "model_preference": "gemini",                   // gemini | claude | auto
  "headless": true,
  "absolute_deadline_unix": null
}
```

## Outputs

```json
{
  "ok": true,
  "task": "Find the price of NVDA on Yahoo Finance",
  "result": {
    "answer": "NVDA: $XXX.XX as of YYYY-MM-DD HH:MM",
    "extracted_data": { "price": "...", "ticker": "NVDA" },
    "url_visited": "https://finance.yahoo.com/quote/NVDA"
  },
  "steps_taken": 6,
  "recoveries": 1,
  "drift_reports": [
    {
      "step": 3,
      "target_label": "search_input",
      "primary_failure": {"selector": "input.search-bar", "strategy": "CSS", "error": "..."},
      "fallback_success": {"selector": "[role='searchbox']", "strategy": "ARIA"},
      "remediation_suggestion": "..."
    }
  ],
  "confidence": 0.87,
  "model_used": "gemini",
  "cost_usd": 0.01,
  "tokens_in": 5000, "tokens_out": 800,
  "elapsed_ms": 28000,
  "trace_id": "tr_browse_xyz",
  "needs_human_review": false,
  "fallback_chain": ["primary", "verify", "next-step"]
}
```

If task fails after all 5 tiers + alternative-site cascade:
```json
{
  "ok": false,
  "needs_human_review": true,
  "reason": "captcha_detected | login_required | site_unreachable | ambiguous_target | budget_exhausted",
  "screenshot_id": "shot_42",
  "last_known_state": "...",
  "drift_reports": [...]
}
```

## 5-tier recovery cascade

For any locator failure within a step:

1. **L1 — Same-selector retry** (network jitter, race condition): retry once after 1s
2. **L2 — Alternative locator strategies**: ARIA label, text content, role+name, vision (LLM looks at screenshot)
3. **L3 — Re-plan**: original plan may have been wrong; re-plan from current page
4. **L4 — Alternative site**: if Skyscanner fails, try Kayak; site_hint as starting point
5. **L5 — Escalate**: emit `needs_human_review: true` with full state dump

## Drift report

A `drift_report.json` entry is written when:
- A primary selector fails AND a fallback strategy succeeds
- A page structure differs from baseline expectations

Drift reports do NOT auto-patch SKILL files (Gemini critique #1: "auto-write code is liability"). They produce machine-readable notes for engineer review.

## When to emit `needs_human_review`

- CAPTCHA detected (any tier 5 strategy can't bypass)
- Login required + no credentials provided
- Confidence < 0.5 after all recoveries
- Same selector failure pattern N+1 times (suggests larger UI change, not transient)
- Budget exhausted

## Cost & latency

| Path | Cost | Latency |
|---|---|---|
| Single-page extraction (happy path) | $0-0.02 | 5-15s |
| Multi-step form fill (5 steps, 0 recoveries) | $0.01-0.05 | 20-40s |
| With drift recovery (1 fallback used) | $0.05-0.10 | 30-60s |
| Full failure → all 5 tiers + escalate | $0.10-0.20 | 90-240s |

## Failure modes

| Mode | Trigger | Handling |
|---|---|---|
| `playwright_not_installed` | browser binary missing | exit 1 with clear install hint |
| `captcha_detected` | CAPTCHA on page | escalate (no auto-solve) |
| `login_required` | login wall, no creds | escalate |
| `budget_exhausted` | LLM budget cap | partial result + warning |
| `timeout` | task > max_runtime_s | partial result, screenshot saved |

## Idempotency

Browser tasks are NOT idempotent (websites change between calls). We DO produce reproducible trace IDs and capture exact state, but re-running the same task may differ.

## How to invoke

```bash
echo '{"task":"Search for OpenAI on google.com and return first result URL"}' | python scripts/run.py
```

## References

- See `references/eval_set.md` — WebVoyager 643 tasks + our custom 30
- See `references/drift_report_schema.md` — full drift report JSON schema
- See `references/recovery_strategies.md` — when each tier kicks in

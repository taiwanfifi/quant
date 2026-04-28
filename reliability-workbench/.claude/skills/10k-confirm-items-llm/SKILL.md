---
name: 10k-confirm-items-llm
description: Tier B confirmation/supplement layer for SEC 10-K item extraction. Takes rules-based candidates + plaintext, asks an LLM to confirm true items, classify status (extracted / incorporated_by_reference / not_applicable / reserved), and add titles. Use when 10k-find-items returns needs_llm_fallback=true OR for any filing requiring authoritative status classification before assembly.
---

# 10-K Confirm Items (Tier B — LLM)

Companion to `10k-find-items` (Tier A). Where rules produce candidates with confidence, this skill **decides** which are real Item headings and what their status is. Single-prompt-per-filing strategy keeps cost ~$0.01-0.04.

## Position in pipeline

```
[10k-fetch] → [10k-find-items] → [10k-confirm-items-llm]  ← THIS
                                              ↓
                          [10k-resolve-incorporation] (only for status=incorporated_by_reference)
                                              ↓
                                       [10k-cross-validate-xbrl]
                                              ↓
                                          [10k-assemble]
```

## When to use

- After `10k-find-items` if `needs_llm_fallback=true` (rules unsure)
- Always, if you want authoritative status classification
- NOT for raw fetching or rule-only fast paths

## Inputs

```json
{
  "filing_path": "/abs/path/to/aapl-20250927.htm",
  "rules_output": {                                  // from 10k-find-items
    "format": "ixbrl",
    "items": [{"item_number":"1A","char_offset":19823,"confidence":0.95,...}],
    "signals": {"form_type":"10-K", ...}
  },
  "model_preference": "auto",                        // auto | claude | gemini
  "max_chars_to_llm": 80000,                         // safety cap on prompt size
  "absolute_deadline_unix": null
}
```

## Outputs

```json
{
  "ok": true,
  "items": [
    {
      "part": "I",
      "item_number": "1",
      "item_title": "Business",
      "char_offset": 19804,
      "char_range_estimated": [19804, 25600],
      "status": "extracted",
      "content_text_preview": "Apple Inc. designs, manufactures...",
      "confidence": 0.92,
      "provenance": {
        "strategy": "llm-confirmed",
        "rules_candidate_used": true,
        "ambiguity_note": null,
        "title_inferred": false
      }
    },
    {
      "part": "III",
      "item_number": "10",
      "item_title": "Directors, Executive Officers and Corporate Governance",
      "char_offset": null,
      "char_range_estimated": null,
      "status": "incorporated_by_reference",
      "content_text_preview": "(content lives in DEF 14A — see 10k-resolve-incorporation)",
      "confidence": 0.88,
      "provenance": {
        "strategy": "llm-confirmed",
        "rules_candidate_used": false,
        "ambiguity_note": null,
        "title_inferred": true
      }
    }
  ],
  "items_total": 23,
  "status_distribution": {
    "extracted": 13,
    "incorporated_by_reference": 4,
    "not_applicable": 1,
    "reserved": 5
  },
  "model_used": "gemini-3-flash",
  "tokens_in": 18000,
  "tokens_out": 1500,
  "cost_usd": 0.0,
  "elapsed_ms": 4200,
  "fallback_chain": ["llm"]
}
```

## How to invoke

```bash
echo '{"filing_path":"...","rules_output":{...}}' | python scripts/run.py
```

## Idempotency

- Cache key: `sha256(filing.raw_hash + rules_output.items_uniq + model_used)`
- Same filing + same rules + same model → identical answer (Claude prompt caching gives near-zero re-cost)

## Failure modes

| Mode | Trigger | Handling |
|---|---|---|
| `llm_unreachable` | All providers fail | exit 1 with error_type |
| `output_unparseable` | LLM returns non-JSON | retry once with stricter prompt; second fail → exit 1 |
| `over_budget` | task exceeds budget | downgrade to cheap model (haiku/gemini-flash) |
| `truncated_doc` | plaintext > max_chars_to_llm | clip + emit warning; LLM should still find item headers (they appear in TOC + first 30K chars) |
| `cookies_expired` | Gemini specific | auto-fallback to Claude if available, else exit |

## Cost & latency

- Typical: 12K-20K tokens in / 1-2K out → ~$0.04 (Sonnet) or $0 (Gemini cookies)
- Worst case: full 200K plaintext + 50 candidates → $0.12 (Sonnet) or $0
- Latency: 3-15s LLM call

## Why one prompt per filing (not per item)

Per-item prompts would be 23x calls × $0.005 = $0.12, with no shared context → can't see TOC patterns. Single prompt: full TOC + all candidates in context, LLM sees structure → better accuracy and cheaper.

Trade-off: ONE big prompt (~80K tokens) is approaching context limit on cheap models. Mitigation: clip to first 80K chars + send TOC + candidates explicitly.

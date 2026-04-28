---
name: 10k-extract-structured
description: End-to-end SEC 10-K extraction. Orchestrates fetch → rule-find → LLM-confirm → IBR-resolve → assemble. Returns the spec-compliant JSON (part / item_number / item_title / content_text / char_range / status) plus provenance + cost trace. Use when user asks for the structured extraction of a 10-K filing, gives a CIK + accession or a filing URL, and wants the full pipeline output.
---

# 10-K Extract Structured (Orchestrator)

The single entry point for Task 3. Internally orchestrates 4 underlying skills:

```
10k-fetch ─→ 10k-find-items (Tier A rules)
                    │
                    ├─ rules confidence ≥ 0.7 ──► 10k-confirm-items-llm (Tier B, optional)
                    └─ rules confidence < 0.7 ──► 10k-confirm-items-llm (Tier B, mandatory)
                                                    │
                                                    └─ for each item with status="incorporated_by_reference"
                                                         └─→ 10k-resolve-incorporation
                                                              │
                                                              └─→ assemble final JSON
```

## When to use

- User provides `{cik, accession}` or `{file_url}` and wants spec-compliant 10-K extraction
- An app/service is calling Task 3 end-to-end
- Use this instead of calling sub-skills directly when you want everything

## Inputs

```json
{
  "cik": "0000320193",
  "accession": "0000320193-25-000079",
  "always_run_llm": false,                  // default: only run Tier B if rules conf < 0.7
  "resolve_incorporation": true,            // default: deep-follow DEF 14A
  "max_chars_to_llm": 80000,
  "model_preference": "auto",
  "absolute_deadline_unix": null
}
```

Or with file URL:
```json
{ "file_url": "https://www.sec.gov/Archives/edgar/data/320193/.../aapl-20250927.htm" }
```

## Outputs (spec-compliant)

```json
{
  "ok": true,
  "trace_id": "tr_extract_aapl_xyz",
  "filing": {
    "cik": "0000320193",
    "accession": "0000320193-25-000079",
    "form_type": "10-K",
    "filed_at": "2025-10-31",
    "primary_doc": "aapl-20250927.htm",
    "raw_hash": "sha256:548ae597..."
  },
  "items": [
    {
      "part": "I",
      "item_number": "1A",
      "item_title": "Risk Factors",
      "content_text": "Apple Inc.'s business is subject to numerous risks...",
      "char_range": [12345, 67890],
      "status": "extracted",
      "confidence": 0.95,
      "provenance": {
        "tier_used": "rules",
        "confidence_signals": ["standard-with-dot", "consecutive_order"],
        "ambiguity_note": null
      }
    },
    {
      "part": "III",
      "item_number": "11",
      "item_title": "Executive Compensation",
      "content_text": "Compensation Discussion and Analysis explains...",
      "char_range": null,
      "status": "incorporated_by_reference",
      "confidence": 0.85,
      "provenance": {
        "tier_used": "ibr-deep-follow",
        "source_doc": {
          "form_type": "DEF 14A",
          "accession": "0001308179-26-000008",
          "filed_at": "2026-01-08"
        },
        "extraction_method": "regex_section_header"
      }
    }
  ],
  "summary": {
    "items_total": 23,
    "status_distribution": {
      "extracted": 13, "incorporated_by_reference": 4,
      "not_applicable": 1, "reserved": 5
    },
    "incorporated_resolved": 4,
    "incorporated_unresolved": 0,
    "total_cost_usd": 0.04,
    "total_elapsed_ms": 18000,
    "tier_distribution": {
      "rules_only": 13,
      "rules_plus_llm": 6,
      "llm_only": 0,
      "ibr_resolved": 4
    }
  },
  "stages": [
    { "stage": "fetch",        "duration_ms": 0,    "from_cache": true },
    { "stage": "find-items",   "duration_ms": 7,    "items_found": 23, "rules_confidence": 1.0 },
    { "stage": "confirm-llm",  "duration_ms": 12000, "skipped": false, "model_used": "gemini-3-flash" },
    { "stage": "resolve-ibr",  "duration_ms": 6000,  "resolved_count": 4 }
  ]
}
```

## Behavior matrix

| Rules confidence | always_run_llm | What runs |
|---|---|---|
| ≥ 0.7 | false (default) | rules → assemble (skip LLM) |
| ≥ 0.7 | true | rules → LLM confirm → assemble |
| < 0.7 | any | rules → LLM confirm (mandatory) → assemble |

For incorporated items, `resolve_incorporation=true` triggers DEF 14A follow.

## Idempotency

Cache key: `sha256(cik + accession + always_run_llm + resolve_incorporation + sub_skill_versions)`. Same input → same output (assuming SEC EDGAR + DEF 14A unchanged).

## Failure modes

| Mode | Trigger | Handling |
|---|---|---|
| `fetch_failed` | 10k-fetch errored | exit with `error_type` |
| `parse_failed` | doc_parser raised | exit with details |
| `llm_unreachable` | both Claude and Gemini down | continue with rules-only output, mark `status: degraded` |
| `partial_ibr` | some incorporated items resolved, some failed | return all items; failed IBRs marked `status: incorporated_by_reference, content_text: null` |

## Cost & latency

| Path | Cost | Latency |
|---|---|---|
| Cache hit, rules sufficient (AAPL happy path) | $0 | < 1s |
| First fetch + rules + LLM confirm + 4 IBR resolve | $0-0.04 | 15-25s |
| Cold + LLM + complex IBR (Item 10 in DEF 14A) | $0.04-0.08 | 30-60s |

## How to invoke

```bash
echo '{"cik":"0000320193","accession":"0000320193-25-000079"}' | python scripts/run.py
```

Or via SkillsRegistry:
```python
sr.execute("10k-extract-structured", {"cik": "0000320193", "accession": "..."})
```

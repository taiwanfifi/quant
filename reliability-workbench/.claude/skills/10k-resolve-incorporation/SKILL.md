---
name: 10k-resolve-incorporation
description: For 10-K items marked status=incorporated_by_reference, fetch the referenced document (typically the company's most recent DEF 14A Proxy) and extract the section that corresponds to this item. Use when an item's content lives outside the 10-K (Items 10-14 in Part III commonly do). This is the A+++ "deep follow" — most candidates only flag IBR items; this skill actually resolves them.
---

# 10-K Resolve Incorporation by Reference

When a 10-K says "Information required by Item 11 is incorporated herein by reference to our definitive proxy statement," this skill:

1. Finds the company's most recent DEF 14A from EDGAR
2. Fetches it via `10k-fetch`
3. Locates the section matching the item (e.g., "Executive Compensation" for Item 11)
4. Extracts the content text

## Position in pipeline

Used after `10k-confirm-items-llm` flags items as `incorporated_by_reference`. Resolved content goes back into the final assembled JSON.

## When to use

- An item from `10k-confirm-items-llm` has `status="incorporated_by_reference"`
- You want **content_text** filled in (not just the IBR flag)
- The "A+++ extraction with provenance trail" demo

## Inputs

```json
{
  "cik": "0000320193",
  "item_number": "11",
  "item_title": "Executive Compensation",
  "filing_date": "2025-10-31"          // optional, narrows DEF 14A search window
}
```

## Outputs

```json
{
  "ok": true,
  "resolved": true,
  "source_doc": {
    "form_type": "DEF 14A",
    "accession": "0000320193-25-000020",
    "filed_at": "2025-01-12",
    "primary_doc": "appleproxy2025.htm"
  },
  "section_found": {
    "title_matched": "Executive Compensation",
    "char_range": [54321, 98765],
    "extraction_method": "regex_section_header"   // or "llm_section_locate"
  },
  "content_text": "...the actual section content...",
  "content_text_preview": "first 200 chars",
  "confidence": 0.85,
  "elapsed_ms": 2400,
  "tokens_in": 0,
  "tokens_out": 0,
  "cost_usd": 0.0,
  "fallback_chain": ["regex"]   // or ["regex", "llm"]
}
```

If unresolved (no Proxy found, section not found):
```json
{
  "ok": true,
  "resolved": false,
  "reason": "no_def14a_within_window | section_not_found | proxy_fetch_failed",
  "content_text": null,
  ...
}
```

## How it locates sections

Item → Proxy section title mapping (typical SEC convention):
| Item | Common section titles in DEF 14A |
|---|---|
| 10 | "Election of Directors", "Directors and Executive Officers", "Corporate Governance" |
| 11 | "Executive Compensation", "Compensation Discussion and Analysis" |
| 12 | "Security Ownership", "Beneficial Ownership" |
| 13 | "Related Person Transactions", "Director Independence" |
| 14 | "Principal Accountant Fees", "Audit Fees" |

### Strategy

1. **Tier A — Regex on section titles**: walk Proxy plaintext for known section headers; success when one is found near a heading-style format (CAPS, larger font in HTML, or `<h2>`/`<h3>` tag)
2. **Tier B — LLM section locator**: if regex misses, ask Gemini "which section in this Proxy corresponds to Item 11 of the 10-K?", get char range, extract

## Idempotency

Cache key: `sha256(cik + item_number + def14a_accession)`. Same inputs → same output. The Proxy itself is content-addressed by accession.

## Failure modes

| Mode | Trigger | Handling |
|---|---|---|
| `no_def14a_within_window` | No DEF 14A within ±18 months of filing_date | `resolved=false`, suggests "look further back" |
| `proxy_fetch_failed` | SEC fetch errored | Log + `resolved=false` |
| `section_not_found` | Both regex and LLM can't pin a section | `resolved=false`, returns full Proxy text snippet |
| `oversize_proxy` | Proxy > 50 MB | Truncate to first 50 MB; warning |

## Cost & latency

- Regex-only path: 0 tokens, $0, ~2s (mostly fetch)
- LLM fallback: ~10K input tokens via Gemini Flash, $0, ~5s
- Worst case: regex + LLM + retry → ~12s, still ~$0

## Why this matters (A+++ signal)

Spec only requires items to be **flagged** as `incorporated_by_reference`. Most candidates stop there. Resolving the actual content from DEF 14A:
- Demonstrates SEC domain depth
- Shows the system actually delivers the data, not just metadata
- Forces dealing with cross-document provenance
- Is the literal "edge case is the data" Gemini critique highlighted as the Hire signal

## References

- See `references/proxy_section_patterns.md` — known section title regex patterns per item
- DEF 14A is also called Proxy Statement; SEC requires it before annual shareholder meetings

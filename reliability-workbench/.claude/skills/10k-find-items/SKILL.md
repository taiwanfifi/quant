---
name: 10k-find-items
description: Find Item boundary candidates in a SEC 10-K filing using rule-based regex (Tier A only). Returns candidates with per-candidate confidence; never the final answer. Use when you have a filing's plaintext and need fast structural candidates before LLM confirmation. Companion to 10k-confirm-items-llm.
---

# 10-K Find Items (Tier A — Rules)

Pure regex-based candidate finder. **Does NOT decide what's correct** — produces a sorted list of candidate Item headings with confidence scores. Caller decides whether to use directly (high confidence) or escalate to LLM (low confidence).

This is the "fast path" of the FLEXIBILITY hybrid pipeline:

```
Tier A (this skill, ~3ms, $0)  → candidates + confidence
       ↓
Tier B (10k-confirm-items-llm) → confirms / supplements when confidence < threshold
       ↓
Tier C (assemble + xbrl-cross-validate) → final structured items
```

## When to use

- After `10k-fetch` returns a `primary_doc_path`
- Want fast structural extraction before paying for LLM
- Want to know "is this a normal 10-K or weird?" via the `needs_llm_fallback` flag

## Inputs

```json
{
  "filing_path": "/abs/path/to/aapl-20250927.htm"
}
```

Or:

```json
{
  "raw_bytes_b64": "..."   // for streaming/no-disk callers
}
```

See `assets/input_schema.json`.

## Outputs

```json
{
  "ok": true,
  "format": "ixbrl",
  "extraction_strategy": "ixbrl-tags-stripped",
  "plaintext_chars": 220598,
  "raw_hash": "sha256:548ae597...",

  "parts_unique": ["I", "II", "III", "IV"],
  "parts_raw_match_count": 21,

  "items": [
    {"item_number": "1", "char_offset": 19804, "matched_text": "Item 1.", "confidence": 0.95, "pattern_used": "standard-with-dot"},
    {"item_number": "1A", "char_offset": 19823, "matched_text": "Item 1A.", "confidence": 0.95, "pattern_used": "standard-with-dot"}
  ],
  "items_unique_count": 23,

  "signals": {
    "incorporated_by_reference_count": 12,
    "reserved_count": 2,
    "is_amendment_indicator": false,
    "envelope_type": "modern",     // "modern" | "pem-sgml-1990s"
    "html_entity_quirks": false    // true if &#160; etc remained pre-decode
  },

  "rules_confidence": 0.92,
  "needs_llm_fallback": false,
  "fallback_reason": null,
  "elapsed_ms": 7
}
```

## Confidence calculation

`rules_confidence` aggregates 5 signals:

| Signal | Weight | Reason |
|---|---|---|
| `parts_unique == 4`? | 0.25 | Standard 10-K has Parts I-IV |
| `items_unique_count >= 14`? | 0.25 | Modern: ≥14, old (1990s): often 14 |
| Standard pattern matches dominate? | 0.20 | "Item 1A." with dot is high-signal |
| Continuous numbering (1, 1A, 1B, 2, 3...)? | 0.15 | Gaps suggest miss |
| No envelope-strip warnings? | 0.15 | clean parse |

Threshold: `< 0.7` → `needs_llm_fallback = true`.

## How to invoke

```bash
echo '{"filing_path": "/path/to/aapl.htm"}' | python scripts/run.py
```

## Idempotency

Pure function of (filing bytes). `raw_hash` in output identifies input. Same bytes → same output.

## Failure modes

| Mode | Trigger | Handling |
|---|---|---|
| `file_not_found` | `filing_path` doesn't exist | exit 1 with clear error |
| `parse_failed` | doc_parser raises | exit 1, suggest LLM fallback |
| `empty_plaintext` | After stripping, no content | `needs_llm_fallback=true`, candidates=[] |
| `rules_low_confidence` | `rules_confidence < 0.7` | success=true but flag set; caller escalates |

## Cost & latency

- Always 0 LLM tokens, $0
- Latency: 3-100ms depending on filing size (1.5 MB iXBRL ≈ 7ms, 10 MB ≈ 70ms)

## Edge cases (see references/edge_cases.md)

- **PFE-style HTML entity quirks**: `ITEM&#160;2.` — handled by doc_parser's `html.unescape()` pre-pass
- **JPM 10-K/A**: returns 0 items, `is_amendment_indicator=true` → caller routes to LLM
- **Ford 1995 PEM/SGML**: doc_parser strips envelope, regex still works on body

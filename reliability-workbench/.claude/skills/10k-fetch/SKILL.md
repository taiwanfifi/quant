---
name: 10k-fetch
description: Download a SEC 10-K filing (HTML, iXBRL, or 1990s plaintext) from EDGAR. Use when user provides a CIK + accession number, mentions SEC EDGAR, asks to fetch a 10-K filing, or starts an extraction pipeline that needs raw filing bytes.
---

# 10-K Fetch

Downloads the **primary document** of a SEC 10-K (or 10-K/A amendment) filing from `data.sec.gov` / `www.sec.gov/Archives/`. Respects SEC's `User-Agent` requirement and 10 req/s rate limit. Returns local path + integrity hash.

## When to use

- "Fetch the 10-K for Apple 2025" (CIK + year given)
- "Download accession 0000320193-25-000079"
- Pipeline calling: extract structured items from filing → first stage is fetch
- User mentions "SEC EDGAR", "10-K filing", "annual report" with company identifier

## Inputs

```json
{
  "cik": "0000320193",                        // 10-digit zero-padded
  "accession": "0000320193-25-000079",        // with dashes
  "force_refresh": false,                     // optional: bypass cache
  "max_size_mb": 50                           // optional: skip if larger
}
```

OR (alternate form):

```json
{
  "file_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm",
  "force_refresh": false
}
```

See `assets/input_schema.json`.

## Outputs

```json
{
  "ok": true,
  "filing_dir": "_cache/sec_filings/AAPL/0000320193-25-000079/",
  "primary_doc_path": "_cache/.../aapl-20250927.htm",
  "primary_doc_url": "https://www.sec.gov/Archives/...",
  "raw_hash": "sha256:548ae597...",
  "size_bytes": 1520208,
  "format_hint": "ixbrl",
  "fetched_at": 1745678901.23,
  "from_cache": false,
  "fetch_strategy": "submissions-api+primary"
}
```

## How to invoke

The skill runs as `python scripts/run.py`. JSON input via stdin → JSON output to stdout.

```bash
echo '{"cik":"0000320193","accession":"0000320193-25-000079"}' \
  | python scripts/run.py
```

Or via `SkillsRegistry.execute("10k-fetch", inputs)`.

## Idempotency

Idempotency key: `sha256(cik + accession + primary_doc)`. Same input → same `primary_doc_path` (cache hit). `force_refresh: true` re-fetches.

## Failure modes

| Mode | Trigger | Handling |
|---|---|---|
| `cik_invalid` | CIK not 10-digit zero-padded | raise SchemaError before fetch |
| `accession_not_found` | submissions API returns no match | exit 1 with `error_type: not_found` |
| `rate_limit_hit` | hit SEC's 10 req/s | session_manager auto-throttles (transparent) |
| `network_timeout` | 30s timeout, retry once with chunked read at 300s | exit 1 if both fail |
| `oversize` | filing > max_size_mb (default 50) | exit 1, suggest streaming |
| `cache_corrupt` | cached file hash mismatch | re-fetch (force_refresh implied) |

## Cost & latency

- Typical: 0 LLM tokens, ~1-3 seconds, $0
- Worst case: 30s timeout + retry = ~33s
- Cached: < 100ms (just hash check)

## Required env

- `SEC_USER_AGENT`: e.g. `"YourName <email@example.com>"` — **mandatory** per SEC policy
- (No API key needed — SEC EDGAR is open data)

## References

- See `references/sec_envelope_formats.md` — modern iXBRL vs 1990s PEM/SGML
- See `references/edge_cases.md` — what to do when primary_doc is `.txt` not `.htm`

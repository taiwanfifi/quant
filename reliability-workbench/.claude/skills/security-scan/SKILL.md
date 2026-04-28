---
name: security-scan
description: Scan a repo for hardcoded secrets (API keys, tokens) and unsafe patterns using trufflehog and basic regex. Returns structured findings. Use when user asks to scan for secrets, check for leaked credentials, run security review, or before publishing a repo.
---

# Security Scan

Detects hardcoded secrets and known vulnerable code patterns. Lighter than a full SAST — focuses on the things that actually leak (AWS keys, GitHub tokens, private keys).

## When to use

- "Scan for leaked secrets"
- "Are there any API keys hardcoded?"
- Pre-release safety check
- Internal: gate Task 2/3 prompt files (no secrets in our prompts/)

## Inputs

```json
{
  "repo_url": "https://github.com/owner/repo",
  "ref": "main",
  "max_runtime_s": 120,
  "scan_depth": "shallow"          // "shallow" (last commit) | "full" (all history, slower)
}
```

## Outputs

```json
{
  "ok": true,
  "repo": "owner/repo",
  "ref": "main",
  "tools_used": ["regex-builtin", "trufflehog"],
  "secrets_found": [
    {
      "type": "AWS_ACCESS_KEY",
      "file": ".env.example",
      "line": 3,
      "preview": "AKIA****",
      "verified": false,
      "matched_by": "regex-builtin"
    }
  ],
  "summary": {
    "verified_secrets": 0,
    "unverified_secrets": 1,
    "total_findings": 1
  },
  "duration_ms": 8000,
  "idempotency_key": "sha256:..."
}
```

## Detection rules

Built-in regex patterns (always run):
- AWS access keys (`AKIA[0-9A-Z]{16}`)
- GitHub tokens (`gh[psoru]_[A-Za-z0-9]{36,}`)
- Slack tokens (`xox[baprs]-[0-9A-Za-z\-]{10,}`)
- Generic high-entropy strings near `secret|key|token|pass`

External (if installed):
- `trufflehog` — verified secret detection (calls APIs to check key validity)

## Failure modes

| Mode | Trigger | Handling |
|---|---|---|
| `clone_failed` | git error | exit 1 |
| `tool_missing` | trufflehog absent | regex-only, mark in `tools_used` |
| `false_positive_filter` | match in `.example` / test fixture | mark `verified: false` |

## Cost & latency

- $0
- shallow: 2-15s; full history: minutes (especially trufflehog)

## Idempotency

`sha256(repo_url + resolved_sha + scan_depth + skill_version)`.

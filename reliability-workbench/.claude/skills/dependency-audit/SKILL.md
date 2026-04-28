---
name: dependency-audit
description: Clone a repo and audit dependencies for known vulnerabilities (pip-audit / npm audit / cargo audit). Returns CVE list with severity. Use when user asks to audit dependencies, check for vulnerabilities, scan supply chain, or before a release. Safe on untrusted repos.
---

# Dependency Audit

Looks at lockfiles + manifests, reports CVEs by severity. Returns counts you can put in a PR comment.

## When to use

- "Audit dependencies on this repo"
- "Check for CVEs"
- Pre-release supply-chain check
- "Are there any known vulnerable packages?"

## Inputs

```json
{
  "repo_url": "https://github.com/owner/repo",
  "ref": "main",
  "severity_threshold": "moderate",   // critical | high | moderate | low
  "max_runtime_s": 120
}
```

## Outputs

```json
{
  "ok": true,
  "repo": "owner/repo",
  "ref": "main",
  "language": "python",
  "tools_used": ["pip-audit"],
  "vulnerabilities": [
    {
      "id": "CVE-2024-12345",
      "package": "requests",
      "installed_version": "2.28.0",
      "fix_available": "2.31.0",
      "severity": "high",
      "summary": "ReDoS in URL parsing"
    }
  ],
  "summary": {
    "critical": 0, "high": 1, "moderate": 3, "low": 7,
    "total": 11
  },
  "above_threshold": 4,
  "duration_ms": 8000,
  "idempotency_key": "sha256:..."
}
```

## How it picks tools

| Detected | Tool |
|---|---|
| `requirements.txt` or `pyproject.toml` | `pip-audit` |
| `package-lock.json` | `npm audit --json` |
| `Cargo.lock` | `cargo audit` |
| Multiple | run all that apply |

## Failure modes

| Mode | Trigger | Handling |
|---|---|---|
| `clone_failed` | git error | exit 1 |
| `tool_missing` | pip-audit / npm / cargo not installed | mark in `tools_used`, fall back to others |
| `no_lockfile` | repo has manifest but no lockfile | warn; pip-audit can still run on requirements.txt |
| `network_required` | tool needs network for advisory DB | retry once |

## Cost & latency

- $0 (no LLM)
- 5-120s depending on dep count + advisory DB freshness

## Idempotency

Cache key: `sha256(repo_url + resolved_sha + tools_used + skill_version)`.

## How to invoke

```bash
echo '{"repo_url":"https://github.com/foo/bar","ref":"main"}' | python scripts/run.py
```

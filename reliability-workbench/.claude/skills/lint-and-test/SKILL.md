---
name: lint-and-test
description: Clone a public Git repo, detect language, run linter (ruff/eslint) and unit tests (pytest/jest), return structured pass/fail JSON. Use when user asks to lint, test, validate a repo, run CI checks, or evaluate a pull request. Safe to run on untrusted repos (subprocess sandbox + timeout).
---

# Lint and Test

End-to-end CI entry point. Clones a repo, detects language, runs the appropriate linter + test runner, returns structured pass/fail.

## When to use

- "Lint and test https://github.com/user/repo"
- "Run CI on this PR"
- "Check if this repo is healthy"
- Internal: gate Task 2/3 evals via `scripts/run.py` (eat-our-dog-food signal)

## Inputs

```json
{
  "repo_url": "https://github.com/owner/repo",
  "ref": "main",                       // branch / tag / SHA
  "lint_only": false,                  // skip tests
  "max_runtime_s": 180,                // hard cap per stage
  "clone_depth": 1,                    // shallow clone
  "language_hint": null                // "python" | "node" | null = auto
}
```

## Outputs

```json
{
  "ok": true,
  "repo": "owner/repo",
  "ref": "main",
  "resolved_sha": "abc123",
  "language": "python",
  "lint": {
    "tool": "ruff",
    "passed": false,
    "error_count": 3,
    "errors": [
      {"file": "src/foo.py", "line": 42, "code": "E501", "message": "line too long"}
    ],
    "duration_ms": 1200
  },
  "test": {
    "tool": "pytest",
    "total": 142,
    "passed": 142,
    "failed": 0,
    "skipped": 0,
    "duration_ms": 18000
  },
  "duration_ms": 38000,
  "idempotency_key": "sha256(repo_url+resolved_sha+skill_v1)"
}
```

## How it picks the right tools

| Detected | Lint | Test |
|---|---|---|
| `pyproject.toml` exists | `ruff check .` | `pytest --tb=short -q` |
| `package.json` exists | `eslint .` (if config) else skip | `npm test` (if `test` script) |
| `Cargo.toml` exists | `cargo clippy --no-deps` | `cargo test` |
| `go.mod` exists | `go vet ./...` | `go test ./...` |
| Otherwise | skip lint | skip test |

## Idempotency

Returns same result for same `(repo_url, resolved_sha, skill_version)`. Resolved SHA freezes the test target — even if `main` advances, repeating the call returns same answer.

## Failure modes

| Mode | Trigger | Handling |
|---|---|---|
| `clone_failed` | git clone errors | exit 1 with stderr |
| `language_undetected` | no recognized manifest | skip lint+test, return `language: "unknown"` |
| `tool_missing` | linter/test runner not installed | skip that stage, mark `tool_missing` |
| `timeout` | exceeds max_runtime_s | partial results, `timed_out: true` |
| `oom` | subprocess killed | mark `oom: true`, suggest increasing limits |

## Cost & latency

- Cost: $0 (no LLM)
- Latency: 5-180s depending on repo size + test suite

## Safety boundary

- Subprocess (no shell=True), scrubbed env, /tmp working dir, hard timeout
- **Known limitation**: `pip install` from cloned repo CAN run setup.py code → small risk
- Production should use Docker backend (stub in `packages/sandbox/`)

## How to invoke

```bash
echo '{"repo_url":"https://github.com/python/cpython","ref":"main"}' | python scripts/run.py
```

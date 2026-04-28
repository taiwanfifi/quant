---
name: build-and-release
description: Cut a new release of a Git repo — bump version, generate changelog from commits, create a Git tag, optionally build artifacts. Use when user asks to release, cut a version, tag a release, or produce release notes from commits. Read-only by default — set `dry_run=false` and provide a write-scope token to actually push.
---

# Build and Release

Walks a repo from "ready to ship" to "tagged release":

1. Determine next version (semver bump from current tag)
2. Collect commits since last tag → categorize into Features / Fixes / Other
3. Generate `RELEASE_NOTES.md` content
4. (Optional) Build artifacts (`python -m build` / `npm pack` / `cargo build --release`)
5. (Optional) Create + push annotated tag

**Default is `dry_run=true`** — returns what WOULD happen without making changes. Production use requires explicit `dry_run=false` + write-scope GitHub token.

## When to use

- "Cut a 0.2.0 release"
- "Generate release notes for these commits"
- "What's new since v0.1.0?"
- Pre-release dry run before manual tagging

## Inputs

```json
{
  "repo_url": "https://github.com/owner/repo",
  "ref": "main",
  "version_bump": "minor",           // major | minor | patch | "v1.2.3" (explicit)
  "dry_run": true,                    // default — no side effects
  "build_artifacts": false,           // default — only changelog + tag plan
  "max_runtime_s": 180
}
```

## Outputs

```json
{
  "ok": true,
  "repo": "owner/repo",
  "ref": "main",
  "current_version": "0.1.0",
  "next_version": "0.2.0",
  "commits_since_last_tag": 23,
  "categorized": {
    "features": [
      {"sha": "abc123", "subject": "feat: add X capability", "author": "Alice"}
    ],
    "fixes": [
      {"sha": "def456", "subject": "fix: handle Y edge case"}
    ],
    "other": [...]
  },
  "release_notes_md": "## v0.2.0 (2026-04-28)\n\n### Features\n- ...",
  "tag_created": false,
  "tag_pushed": false,
  "artifacts_built": [],
  "dry_run": true,
  "duration_ms": 4000,
  "idempotency_key": "sha256:..."
}
```

## Version bump logic

- `major` (`X.y.z → X+1.0.0`): breaking changes
- `minor` (`x.Y.z → x.Y+1.0`): new features
- `patch` (`x.y.Z → x.y.Z+1`): bug fixes
- explicit `v1.2.3`: caller specifies

If repo has no existing tags → starts at `v0.1.0`.

## Commit categorization

Conventional Commits prefix → category:
- `feat:`, `feature:` → Features
- `fix:`, `bug:` → Fixes
- `chore:`, `docs:`, `refactor:`, `test:`, `style:` → Other

Non-conventional commits → "Other" with full subject.

## Safety boundaries

- **Default `dry_run=true`** — read-only
- For `dry_run=false`, requires `GITHUB_TOKEN` env with `contents:write` scope
- Never force-pushes
- Never removes tags
- Never modifies existing release notes (only creates new)

## Failure modes

| Mode | Trigger | Handling |
|---|---|---|
| `clone_failed` | git error | exit 1 |
| `no_commits_since_last_tag` | already up to date | report `next_version: current_version`, suggest no-op |
| `tag_already_exists` | `dry_run=false` + tag exists | exit 1, never overwrite |
| `dirty_workdir` | uncommitted changes | not applicable (we operate on shallow clone) |
| `auth_failed` | push needs token | clear error suggesting GITHUB_TOKEN scope |

## Cost & latency

- $0 (no LLM)
- 5-30s for shallow clone + git log + version compute
- + minutes if `build_artifacts=true` and project has heavy build (e.g., Rust release builds)

## Idempotency

Cache key: `sha256(repo_url + resolved_sha + version_bump + dry_run + skill_version)`.
Same input → same output (dry-run mode is naturally idempotent; tag creation is one-way).

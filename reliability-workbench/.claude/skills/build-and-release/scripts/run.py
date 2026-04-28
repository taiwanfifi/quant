#!/usr/bin/env python3
"""build-and-release: clone → semver bump → categorize commits → release notes → optional tag."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from packages.sandbox import execute  # noqa: E402

SKILL_VERSION = "build-and-release-v0.1"

CONV_PREFIX_RE = re.compile(
    r"^(?P<type>feat|feature|fix|bug|chore|docs|refactor|test|style|perf|build|ci)(?:\([^)]*\))?:\s*(?P<subject>.+)$",
    re.IGNORECASE,
)


def _err(t, m, **kw):
    return {
        "ok": False, "repo": "", "ref": "",
        "current_version": "", "next_version": "",
        "categorized": {"features": [], "fixes": [], "other": []},
        "release_notes_md": "", "dry_run": True,
        "duration_ms": 0, "idempotency_key": "",
        "error_type": t, "error_message": m, **kw,
    }


def _parse_version(tag: str) -> tuple[int, int, int] | None:
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", tag.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _bump_version(current: tuple[int, int, int], bump: str) -> tuple[int, int, int]:
    explicit = _parse_version(bump)
    if explicit is not None:
        return explicit
    M, m_, p = current
    if bump == "major":
        return (M + 1, 0, 0)
    if bump == "minor":
        return (M, m_ + 1, 0)
    if bump == "patch":
        return (M, m_, p + 1)
    raise ValueError(f"unknown version_bump: {bump}")


def _categorize_commits(commits: list[dict]) -> dict:
    out = {"features": [], "fixes": [], "other": []}
    for c in commits:
        m = CONV_PREFIX_RE.match(c["subject"])
        if m:
            t = m.group("type").lower()
            subj = m.group("subject")
            entry = {**c, "subject": subj, "type": t}
            if t in ("feat", "feature"):
                out["features"].append(entry)
            elif t in ("fix", "bug"):
                out["fixes"].append(entry)
            else:
                out["other"].append(entry)
        else:
            out["other"].append({**c, "type": "uncategorized"})
    return out


def _format_release_notes(next_v: str, date_str: str, cats: dict) -> str:
    lines = [f"## {next_v} ({date_str})", ""]
    if cats["features"]:
        lines.append("### Features")
        for c in cats["features"]:
            lines.append(f"- {c['subject']} ({c['sha'][:7]}{', @' + c['author'] if c.get('author') else ''})")
        lines.append("")
    if cats["fixes"]:
        lines.append("### Fixes")
        for c in cats["fixes"]:
            lines.append(f"- {c['subject']} ({c['sha'][:7]}{', @' + c['author'] if c.get('author') else ''})")
        lines.append("")
    if cats["other"]:
        lines.append("### Other")
        for c in cats["other"]:
            lines.append(f"- {c['subject']} ({c['sha'][:7]})")
        lines.append("")
    return "\n".join(lines)


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps(_err("input_empty", "no JSON on stdin"))); sys.exit(1)
    try:
        inputs = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps(_err("input_invalid_json", str(e)))); sys.exit(1)

    t0 = time.time()
    repo_url = inputs["repo_url"]
    ref = inputs.get("ref", "main")
    bump = inputs.get("version_bump", "minor")
    dry_run = bool(inputs.get("dry_run", True))
    build_artifacts = bool(inputs.get("build_artifacts", False))
    timeout = int(inputs.get("max_runtime_s", 180))

    repo_short = re.sub(r"^https?://(?:[^/]+/)+", "", repo_url).rstrip("/").removesuffix(".git")

    workdir = Path(tempfile.mkdtemp(prefix="build-release-"))
    try:
        # 1. Full(ish) clone — need history for version + commit list
        clone = execute(["git", "clone", "--filter=blob:none", repo_url, str(workdir / "repo")],
                         timeout_s=120)
        if clone.returncode != 0:
            print(json.dumps(_err("clone_failed", clone.stderr[:300])))
            sys.exit(1)
        execute(["git", "-C", str(workdir / "repo"), "checkout", ref], timeout_s=30)

        repo_dir = workdir / "repo"
        sha = execute(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], timeout_s=10).stdout.strip()[:40]

        # 2. Get latest tag
        latest_tag_proc = execute(
            ["git", "-C", str(repo_dir), "describe", "--tags", "--abbrev=0"], timeout_s=10
        )
        if latest_tag_proc.returncode == 0:
            current_tag = latest_tag_proc.stdout.strip()
            current_v_tuple = _parse_version(current_tag) or (0, 0, 0)
        else:
            current_tag = "(none)"
            current_v_tuple = (0, 0, 0)

        # 3. Bump
        try:
            next_v_tuple = _bump_version(current_v_tuple, bump)
        except ValueError as e:
            print(json.dumps(_err("invalid_bump", str(e))))
            sys.exit(1)
        next_version = f"v{next_v_tuple[0]}.{next_v_tuple[1]}.{next_v_tuple[2]}"
        current_version = current_tag if current_tag != "(none)" else "v0.0.0"

        # 4. List commits since last tag (or all commits if no tag)
        if current_tag != "(none)":
            log_range = f"{current_tag}..HEAD"
        else:
            log_range = "HEAD"
        log_proc = execute(
            ["git", "-C", str(repo_dir), "log", log_range,
             "--format=%H%x09%s%x09%an", "--max-count=200"],
            timeout_s=20,
        )
        commits = []
        for line in log_proc.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            commits.append({
                "sha": parts[0],
                "subject": parts[1],
                "author": parts[2] if len(parts) > 2 else "",
            })

        cats = _categorize_commits(commits)

        # 5. Release notes
        date_str = dt.datetime.utcnow().strftime("%Y-%m-%d")
        notes = _format_release_notes(next_version, date_str, cats)

        # 6. Artifacts (if requested)
        artifacts_built: list[str] = []
        warnings: list[str] = []
        if build_artifacts and not dry_run:
            if (repo_dir / "pyproject.toml").exists():
                r = execute(["python", "-m", "build", "--outdir", str(workdir / "dist")],
                             timeout_s=timeout, cwd=repo_dir)
                if r.returncode == 0:
                    artifacts_built = [f.name for f in (workdir / "dist").glob("*")]
                else:
                    warnings.append(f"python build failed: {r.stderr[:200]}")
            elif (repo_dir / "package.json").exists():
                r = execute(["npm", "pack"], timeout_s=timeout, cwd=repo_dir,
                             pass_env_keys={"npm_config_cache"})
                if r.returncode == 0:
                    artifacts_built = re.findall(r"(\S+\.tgz)", r.stdout)
                else:
                    warnings.append(f"npm pack failed: {r.stderr[:200]}")

        # 7. Tag (only if explicitly NOT dry-run)
        tag_created = False
        tag_pushed = False
        if not dry_run:
            r = execute(["git", "-C", str(repo_dir), "rev-parse", next_version], timeout_s=5)
            if r.returncode == 0:
                print(json.dumps(_err("tag_already_exists",
                                        f"tag {next_version} already exists; never overwrite")))
                sys.exit(1)
            r = execute(["git", "-C", str(repo_dir), "tag", "-a", next_version,
                          "-m", f"Release {next_version}"], timeout_s=10)
            tag_created = r.returncode == 0
            if not tag_created:
                warnings.append(f"tag creation failed: {r.stderr[:200]}")
            # We do NOT push — caller's repo is a temp clone. They can pull notes / sha to push.

        idem = "sha256:" + hashlib.sha256(
            f"{repo_url}@{sha}@{bump}@{dry_run}@{SKILL_VERSION}".encode()
        ).hexdigest()

        out = {
            "ok": True, "repo": repo_short, "ref": ref,
            "resolved_sha": sha,
            "current_version": current_version,
            "next_version": next_version,
            "commits_since_last_tag": len(commits),
            "categorized": cats,
            "release_notes_md": notes,
            "tag_created": tag_created,
            "tag_pushed": tag_pushed,
            "artifacts_built": artifacts_built,
            "dry_run": dry_run,
            "duration_ms": int((time.time() - t0) * 1000),
            "idempotency_key": idem,
            "warnings": warnings,
        }
        print(json.dumps(out))
        sys.exit(0)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""security-scan: clone → builtin regex + trufflehog (optional) → structured findings."""
from __future__ import annotations

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

from packages.sandbox import execute, SandboxBackendError  # noqa: E402

SKILL_VERSION = "security-scan-v0.1"

SECRET_PATTERNS = [
    ("AWS_ACCESS_KEY", re.compile(r"\b(AKIA[0-9A-Z]{16})\b")),
    ("AWS_SECRET",     re.compile(r"\b([0-9a-zA-Z/+=]{40})\b(?=.*aws|.*secret)")),
    ("GITHUB_TOKEN",   re.compile(r"\b(gh[psoru]_[A-Za-z0-9]{36,})\b")),
    ("SLACK_TOKEN",    re.compile(r"\b(xox[baprs]-[A-Za-z0-9\-]{10,})\b")),
    ("PRIVATE_KEY",    re.compile(r"-----BEGIN (RSA|OPENSSH|DSA|EC) PRIVATE KEY-----")),
    ("ANTHROPIC_KEY",  re.compile(r"\b(sk-ant-[A-Za-z0-9_\-]{95,})\b")),
    ("OPENAI_KEY",     re.compile(r"\b(sk-[A-Za-z0-9]{48})\b")),
    ("GOOGLE_API",     re.compile(r"\b(AIza[A-Za-z0-9_\-]{35})\b")),
    ("STRIPE_KEY",     re.compile(r"\b(sk_live_[A-Za-z0-9]{24,})\b")),
]

# Patterns we always EXCLUDE (false positives)
FP_PATH_PATTERNS = (".example", ".sample", "test/fixtures/", "tests/fixtures/",
                     "_test.py", "test_", "/docs/", "README", "CHANGELOG")


def _err(t, m, **kw):
    return {"ok": False, "repo": "", "ref": "", "tools_used": [],
             "secrets_found": [],
             "summary": {"verified_secrets": 0, "unverified_secrets": 0, "total_findings": 0},
             "duration_ms": 0, "idempotency_key": "",
             "error_type": t, "error_message": m, **kw}


def is_likely_fp(file_path: str) -> bool:
    f = file_path.lower()
    return any(p in f for p in FP_PATH_PATTERNS)


def scan_regex(repo_dir: Path) -> list[dict]:
    findings: list[dict] = []
    for f in repo_dir.rglob("*"):
        if not f.is_file() or f.stat().st_size > 1024 * 1024:  # skip > 1 MB
            continue
        rel = str(f.relative_to(repo_dir))
        if rel.startswith(".git/"):
            continue
        # Skip binary
        try:
            text = f.read_text(errors="ignore")
        except Exception:
            continue
        for kind, pat in SECRET_PATTERNS:
            for m in pat.finditer(text):
                # Compute line number
                line_no = text[:m.start()].count("\n") + 1
                preview = m.group(0)[:8] + "****"
                findings.append({
                    "type": kind,
                    "file": rel,
                    "line": line_no,
                    "preview": preview,
                    "verified": False,
                    "matched_by": "regex-builtin",
                    "is_likely_false_positive": is_likely_fp(rel),
                })
    return findings


def scan_trufflehog(repo_dir: Path, timeout: int, full_history: bool) -> tuple[list[dict], str | None]:
    """Run trufflehog if available. Returns (findings, error)."""
    args = ["trufflehog"]
    if full_history:
        args += ["git", str(repo_dir)]
    else:
        args += ["filesystem", str(repo_dir)]
    args += ["--json"]
    try:
        r = execute(args, timeout_s=timeout)
    except SandboxBackendError as e:
        return [], f"trufflehog not installed: {e}"
    if r.returncode not in (0, 183):  # 183 = trufflehog "secrets found"
        return [], r.stderr[:200]
    findings = []
    for line in r.stdout.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        meta = (obj.get("SourceMetadata") or {}).get("Data", {}).get("Filesystem") or \
                (obj.get("SourceMetadata") or {}).get("Data", {}).get("Git") or {}
        findings.append({
            "type": obj.get("DetectorName", "UNKNOWN").upper(),
            "file": meta.get("file", "")[len(str(repo_dir))+1:] if meta.get("file") else "",
            "line": meta.get("line", 0),
            "preview": (obj.get("Raw") or "")[:8] + "****",
            "verified": bool(obj.get("Verified", False)),
            "matched_by": "trufflehog",
        })
    return findings, None


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
    timeout = int(inputs.get("max_runtime_s", 120))
    scan_depth = inputs.get("scan_depth", "shallow")

    repo_short = re.sub(r"^https?://(?:[^/]+/)+", "", repo_url).rstrip("/").removesuffix(".git")
    workdir = Path(tempfile.mkdtemp(prefix="security-scan-"))
    try:
        clone_depth = "1" if scan_depth == "shallow" else "100"
        clone_args = ["git", "clone", "--depth", clone_depth,
                       "--branch", ref, repo_url, str(workdir / "repo")]
        clone = execute(clone_args, timeout_s=60)
        if clone.returncode != 0:
            clone_args2 = ["git", "clone", "--depth", clone_depth, repo_url, str(workdir / "repo")]
            clone = execute(clone_args2, timeout_s=60)
            if clone.returncode != 0:
                print(json.dumps(_err("clone_failed", clone.stderr[:300])))
                sys.exit(1)
            execute(["git", "-C", str(workdir / "repo"), "checkout", ref], timeout_s=30)

        repo_dir = workdir / "repo"
        sha = execute(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], timeout_s=10).stdout.strip()[:40]

        all_findings: list[dict] = []
        tools_used: list[str] = []
        warnings: list[str] = []

        # 1. Built-in regex (always)
        regex_findings = scan_regex(repo_dir)
        all_findings.extend(regex_findings)
        tools_used.append("regex-builtin")

        # 2. trufflehog (optional)
        th_findings, th_err = scan_trufflehog(repo_dir, timeout, scan_depth == "full")
        if th_err:
            warnings.append(f"trufflehog: {th_err}")
        else:
            tools_used.append("trufflehog")
            all_findings.extend(th_findings)

        # 3. Dedup (same file+line+type)
        seen = set()
        deduped = []
        for f in all_findings:
            key = (f.get("file"), f.get("line"), f.get("type"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(f)

        verified = sum(1 for f in deduped if f.get("verified"))
        unverified = len(deduped) - verified
        summary = {"verified_secrets": verified, "unverified_secrets": unverified,
                    "total_findings": len(deduped),
                    "false_positives_filtered": sum(1 for f in deduped
                                                       if f.get("is_likely_false_positive"))}

        idem = "sha256:" + hashlib.sha256(
            f"{repo_url}@{sha}@{scan_depth}@{SKILL_VERSION}".encode()
        ).hexdigest()

        out = {
            "ok": True, "repo": repo_short, "ref": ref,
            "resolved_sha": sha,
            "tools_used": tools_used,
            "secrets_found": deduped[:200],
            "summary": summary,
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

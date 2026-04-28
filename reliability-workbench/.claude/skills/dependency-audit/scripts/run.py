#!/usr/bin/env python3
"""dependency-audit: clone → run pip-audit / npm audit / cargo audit → structured CVEs."""
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

from packages.sandbox import execute  # noqa: E402

SKILL_VERSION = "dependency-audit-v0.1"
SEVERITY_RANK = {"low": 1, "moderate": 2, "high": 3, "critical": 4}


def _err(t, m, **kw):
    return {"ok": False, "repo": "", "ref": "", "tools_used": [],
             "summary": {"critical":0,"high":0,"moderate":0,"low":0,"total":0},
             "duration_ms": 0, "idempotency_key": "",
             "error_type": t, "error_message": m, **kw}


def _detect_lockfiles(repo_dir: Path) -> dict[str, bool]:
    return {
        "python_pip": (repo_dir / "requirements.txt").exists(),
        "python_pyproject": (repo_dir / "pyproject.toml").exists(),
        "node": (repo_dir / "package-lock.json").exists() or (repo_dir / "package.json").exists(),
        "rust": (repo_dir / "Cargo.lock").exists(),
    }


def run_pip_audit(repo_dir: Path, timeout: int) -> tuple[list[dict], str | None]:
    """Run pip-audit. Returns (vulnerabilities, error_msg)."""
    # Try requirements.txt first; fall back to project install
    req = repo_dir / "requirements.txt"
    if req.exists():
        cmd = ["pip-audit", "-r", str(req), "--format", "json", "--progress-spinner", "off"]
    else:
        cmd = ["pip-audit", "--format", "json", "--progress-spinner", "off"]
    r = execute(cmd, timeout_s=timeout, cwd=repo_dir)
    if r.returncode not in (0, 1):
        return [], r.stderr[:200]
    try:
        data = json.loads(r.stdout) if r.stdout.strip() else {"dependencies": []}
    except json.JSONDecodeError:
        return [], "pip-audit JSON parse failed"

    vulns = []
    for dep in data.get("dependencies", []):
        for v in dep.get("vulns", []):
            vulns.append({
                "id": v.get("id", "UNKNOWN"),
                "package": dep.get("name", ""),
                "installed_version": dep.get("version", ""),
                "fix_available": ", ".join(v.get("fix_versions", []) or []) or None,
                "severity": "moderate",  # pip-audit doesn't always provide; default
                "summary": v.get("description", "")[:300],
            })
    return vulns, None


def run_npm_audit(repo_dir: Path, timeout: int) -> tuple[list[dict], str | None]:
    if not (repo_dir / "package.json").exists():
        return [], "no package.json"
    r = execute(["npm", "audit", "--json"], timeout_s=timeout, cwd=repo_dir,
                 pass_env_keys={"npm_config_cache"})
    if r.returncode not in (0, 1):
        return [], r.stderr[:200]
    try:
        data = json.loads(r.stdout) if r.stdout.strip() else {}
    except json.JSONDecodeError:
        return [], "npm audit JSON parse failed"
    vulns = []
    for name, info in (data.get("vulnerabilities") or {}).items():
        if not isinstance(info, dict):
            continue
        sev = (info.get("severity") or "low").lower()
        sev = "moderate" if sev == "moderate" else sev
        if sev not in SEVERITY_RANK:
            sev = "low"
        for v in (info.get("via") or []):
            if isinstance(v, dict):
                vulns.append({
                    "id": v.get("source") or v.get("name") or "UNKNOWN",
                    "package": name,
                    "installed_version": info.get("range", ""),
                    "fix_available": (info.get("fixAvailable") if isinstance(info.get("fixAvailable"), str) else None),
                    "severity": sev,
                    "summary": (v.get("title") or "")[:300],
                })
    return vulns, None


def run_cargo_audit(repo_dir: Path, timeout: int) -> tuple[list[dict], str | None]:
    if not (repo_dir / "Cargo.lock").exists():
        return [], "no Cargo.lock"
    r = execute(["cargo", "audit", "--json"], timeout_s=timeout, cwd=repo_dir)
    if r.returncode not in (0, 1):
        return [], r.stderr[:200]
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return [], "cargo audit JSON parse failed"
    vulns = []
    for v in data.get("vulnerabilities", {}).get("list", []):
        adv = v.get("advisory") or {}
        vulns.append({
            "id": adv.get("id", "UNKNOWN"),
            "package": (v.get("package") or {}).get("name", ""),
            "installed_version": (v.get("package") or {}).get("version", ""),
            "fix_available": ", ".join(v.get("versions", {}).get("patched", []) or []) or None,
            "severity": "high",  # cargo-audit doesn't always tag; conservative
            "summary": adv.get("title", "")[:300],
        })
    return vulns, None


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
    threshold = inputs.get("severity_threshold", "moderate")
    timeout = int(inputs.get("max_runtime_s", 120))

    repo_short = re.sub(r"^https?://(?:[^/]+/)+", "", repo_url).rstrip("/").removesuffix(".git")

    workdir = Path(tempfile.mkdtemp(prefix="dep-audit-"))
    try:
        # 1. clone
        clone_args = ["git", "clone", "--depth", "1",
                       "--branch", ref, repo_url, str(workdir / "repo")]
        clone = execute(clone_args, timeout_s=60)
        if clone.returncode != 0:
            clone_args2 = ["git", "clone", "--depth", "1", repo_url, str(workdir / "repo")]
            clone = execute(clone_args2, timeout_s=60)
            if clone.returncode != 0:
                print(json.dumps(_err("clone_failed", clone.stderr[:300])))
                sys.exit(1)
            execute(["git", "-C", str(workdir / "repo"), "checkout", ref], timeout_s=30)

        repo_dir = workdir / "repo"

        sha = execute(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], timeout_s=10).stdout.strip()[:40]

        # 2. detect lockfiles + run tools
        lockfiles = _detect_lockfiles(repo_dir)
        all_vulns: list[dict] = []
        tools_used: list[str] = []
        warnings: list[str] = []

        if lockfiles["python_pip"] or lockfiles["python_pyproject"]:
            v, err = run_pip_audit(repo_dir, timeout)
            if err:
                warnings.append(f"pip-audit: {err}")
            else:
                tools_used.append("pip-audit")
                all_vulns.extend(v)
        if lockfiles["node"]:
            v, err = run_npm_audit(repo_dir, timeout)
            if err:
                warnings.append(f"npm audit: {err}")
            else:
                tools_used.append("npm audit")
                all_vulns.extend(v)
        if lockfiles["rust"]:
            v, err = run_cargo_audit(repo_dir, timeout)
            if err:
                warnings.append(f"cargo audit: {err}")
            else:
                tools_used.append("cargo audit")
                all_vulns.extend(v)

        # 3. summarize
        summary = {"critical": 0, "high": 0, "moderate": 0, "low": 0, "total": 0}
        for v in all_vulns:
            s = v.get("severity", "low")
            if s in summary:
                summary[s] += 1
                summary["total"] += 1

        threshold_rank = SEVERITY_RANK.get(threshold, 2)
        above_threshold = sum(1 for v in all_vulns
                                if SEVERITY_RANK.get(v.get("severity", "low"), 1) >= threshold_rank)

        # 4. determine language for reporting
        lang = "unknown"
        if "pip-audit" in tools_used: lang = "python"
        elif "npm audit" in tools_used: lang = "node"
        elif "cargo audit" in tools_used: lang = "rust"

        idem = "sha256:" + hashlib.sha256(
            f"{repo_url}@{sha}@{','.join(tools_used)}@{SKILL_VERSION}".encode()
        ).hexdigest()

        out = {
            "ok": True, "repo": repo_short, "ref": ref,
            "resolved_sha": sha, "language": lang,
            "tools_used": tools_used,
            "vulnerabilities": all_vulns[:200],  # cap
            "summary": summary,
            "above_threshold": above_threshold,
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

#!/usr/bin/env python3
"""lint-and-test: clone → detect language → run lint + tests → structured JSON."""
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

from packages.sandbox import execute, ProcessResult, SandboxBackendError  # noqa: E402

SKILL_VERSION = "lint-and-test-v0.1"


def _err(t: str, m: str, **kw) -> dict:
    return {"ok": False, "repo": "", "ref": "", "language": "unknown",
             "duration_ms": 0, "idempotency_key": "",
             "error_type": t, "error_message": m, **kw}


def _detect_language(repo_dir: Path, hint: str | None) -> str:
    if hint:
        return hint
    if (repo_dir / "pyproject.toml").exists() or (repo_dir / "setup.py").exists():
        return "python"
    if (repo_dir / "package.json").exists():
        return "node"
    if (repo_dir / "Cargo.toml").exists():
        return "rust"
    if (repo_dir / "go.mod").exists():
        return "go"
    return "unknown"


def _parse_pytest_summary(stdout: str) -> dict:
    """Parse pytest summary line. e.g. '142 passed in 18.32s' or '3 failed, 139 passed'."""
    summary = {"total": 0, "passed": 0, "failed": 0, "skipped": 0}
    # Most reliable: last line matches "X passed", "X failed" etc.
    for line in reversed(stdout.splitlines()):
        if "passed" in line or "failed" in line or "error" in line:
            for n, kind in re.findall(r"(\d+)\s+(passed|failed|skipped|error)", line):
                kind = kind.replace("error", "failed")
                summary[kind] = summary.get(kind, 0) + int(n)
            break
    summary["total"] = summary["passed"] + summary["failed"] + summary["skipped"]
    return summary


def _parse_ruff(stdout: str) -> list[dict]:
    """Ruff outputs: src/foo.py:42:1: E501 Line too long..."""
    errors = []
    for line in stdout.splitlines():
        m = re.match(r"^(.+):(\d+):(\d+):\s+(\w+)\s+(.+)$", line)
        if m:
            errors.append({"file": m.group(1), "line": int(m.group(2)),
                            "col": int(m.group(3)), "code": m.group(4),
                            "message": m.group(5)})
    return errors


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
    lint_only = bool(inputs.get("lint_only", False))
    max_runtime = int(inputs.get("max_runtime_s", 180))
    clone_depth = int(inputs.get("clone_depth", 1))
    hint = inputs.get("language_hint")

    repo_short = re.sub(r"^https?://(?:[^/]+/)+", "", repo_url).rstrip("/").removesuffix(".git")

    # 1. Clone
    workdir = Path(tempfile.mkdtemp(prefix="lint-and-test-"))
    try:
        clone_args = ["git", "clone", "--depth", str(clone_depth),
                       "--branch", ref, repo_url, str(workdir / "repo")]
        clone = execute(clone_args, timeout_s=60, pass_env_keys={"GITHUB_TOKEN"})
        if clone.returncode != 0:
            # Retry without --branch (tag/sha case)
            clone_args2 = ["git", "clone", "--depth", str(clone_depth),
                            repo_url, str(workdir / "repo")]
            clone = execute(clone_args2, timeout_s=60, pass_env_keys={"GITHUB_TOKEN"})
            if clone.returncode != 0:
                print(json.dumps(_err("clone_failed", clone.stderr[:500])))
                sys.exit(1)
            # Then checkout ref
            execute(["git", "-C", str(workdir / "repo"), "checkout", ref], timeout_s=30)

        repo_dir = workdir / "repo"

        # 2. Resolve SHA
        sha_proc = execute(["git", "-C", str(repo_dir), "rev-parse", "HEAD"], timeout_s=10)
        resolved_sha = sha_proc.stdout.strip()[:40] if sha_proc.returncode == 0 else "unknown"

        # 3. Detect language
        language = _detect_language(repo_dir, hint)

        result: dict = {
            "ok": True, "repo": repo_short, "ref": ref,
            "resolved_sha": resolved_sha, "language": language,
            "warnings": [],
        }

        # 4. Lint
        lint_result = None
        if language == "python":
            r = execute(["ruff", "check", "."], timeout_s=max_runtime, cwd=repo_dir)
            if r.returncode in (0, 1):  # 0=clean, 1=found issues
                errors = _parse_ruff(r.stdout)
                lint_result = {
                    "tool": "ruff", "passed": r.returncode == 0,
                    "error_count": len(errors),
                    "errors": errors[:50],  # cap
                    "duration_ms": r.duration_ms,
                }
            else:
                lint_result = {"tool": "ruff", "passed": False,
                                "error_count": 0, "errors": [],
                                "tool_missing_or_error": True,
                                "stderr_preview": r.stderr[:200],
                                "duration_ms": r.duration_ms}
        elif language == "node":
            r = execute(["npx", "--yes", "eslint", "."], timeout_s=max_runtime,
                         cwd=repo_dir, pass_env_keys={"npm_config_cache"})
            lint_result = {"tool": "eslint", "passed": r.returncode == 0,
                            "stdout_preview": r.stdout[:500],
                            "duration_ms": r.duration_ms}
        else:
            result["warnings"].append(f"lint skipped: language={language}")

        if lint_result:
            result["lint"] = lint_result

        # 5. Test
        if not lint_only:
            test_result = None
            if language == "python":
                r = execute(["pytest", "--tb=short", "-q"],
                             timeout_s=max_runtime, cwd=repo_dir)
                summary = _parse_pytest_summary(r.stdout + "\n" + r.stderr)
                test_result = {
                    "tool": "pytest",
                    "passed": r.returncode == 0,
                    **summary,
                    "duration_ms": r.duration_ms,
                    "timed_out": r.timed_out,
                }
            elif language == "node":
                r = execute(["npm", "test"], timeout_s=max_runtime, cwd=repo_dir,
                             pass_env_keys={"npm_config_cache"})
                test_result = {"tool": "npm test",
                                "passed": r.returncode == 0,
                                "stdout_preview": r.stdout[:500],
                                "duration_ms": r.duration_ms}
            else:
                result["warnings"].append(f"test skipped: language={language}")

            if test_result:
                result["test"] = test_result

        # 6. Idempotency key
        idem_basis = f"{repo_url}@{resolved_sha}@{SKILL_VERSION}@{lint_only}"
        result["idempotency_key"] = "sha256:" + hashlib.sha256(idem_basis.encode()).hexdigest()

        result["duration_ms"] = int((time.time() - t0) * 1000)
        print(json.dumps(result))
        sys.exit(0)

    except SandboxBackendError as e:
        print(json.dumps(_err("sandbox_error", str(e)))); sys.exit(1)
    except Exception as e:
        print(json.dumps(_err("unexpected", str(e)))); sys.exit(1)
    finally:
        try:
            shutil.rmtree(workdir, ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()

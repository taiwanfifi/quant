#!/usr/bin/env python3
"""zeabur-deploy: wraps `npx zeabur@latest` CLI with token-from-env."""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from packages.sandbox import execute  # noqa: E402

SKILL_VERSION = "zeabur-deploy-v0.1"


def _load_env_dotenv():
    """Best-effort: load /Users/william/Downloads/quant/.env if present (not committed)."""
    candidates = [
        REPO_ROOT.parent / ".env",
        REPO_ROOT / ".env",
    ]
    for env_path in candidates:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                # Don't overwrite if already in env
                os.environ.setdefault(k, v)
            return env_path
    return None


def _err(t: str, m: str, **kw) -> dict:
    return {"ok": False, "action": kw.pop("action", ""),
             "elapsed_ms": 0,
             "error_type": t, "error_message": m, **kw}


def _scrub_token(text: str, token: str) -> str:
    """Remove token from any output."""
    if not token or not text:
        return text
    return text.replace(token, "***ZEABUR_TOKEN***")


def _run_zeabur(args: list[str], token: str, *, timeout: int = 300) -> tuple[int, str, str]:
    """Run npx zeabur with token via env (more secure than --token flag in argv)."""
    full_args = ["npx", "zeabur@latest", *args, "-i=false"]
    env = {"ZEABUR_TOKEN": token, "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", "")}
    proc = execute(full_args, timeout_s=timeout,
                    cwd=REPO_ROOT,
                    env=env,
                    pass_env_keys={"PATH", "HOME", "USER", "SHELL", "NODE_PATH",
                                    "npm_config_cache"})
    return proc.returncode, _scrub_token(proc.stdout, token), _scrub_token(proc.stderr, token)


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps(_err("input_empty", "no JSON on stdin"))); sys.exit(1)
    try:
        inputs = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps(_err("input_invalid_json", str(e)))); sys.exit(1)

    _load_env_dotenv()
    action = inputs["action"]
    timeout = int(inputs.get("max_runtime_s", 300))

    token = os.environ.get("ZEABUR_TOKEN")
    if not token:
        print(json.dumps(_err("auth_required",
                                "ZEABUR_TOKEN not set; "
                                "run `npx zeabur@latest auth login` or "
                                "set in .env",
                                action=action)))
        sys.exit(1)

    if not shutil.which("npx"):
        print(json.dumps(_err("npx_not_found",
                                "npx not in PATH; install Node.js",
                                action=action)))
        sys.exit(1)

    t0 = time.time()
    out: dict = {"ok": False, "action": action}

    try:
        if action == "auth-check":
            # Probe via list-projects (cheap, doesn't deploy anything)
            rc, sout, serr = _run_zeabur(["project", "ls"], token, timeout=30)
            out["ok"] = (rc == 0)
            out["stdout_tail"] = sout[-2000:]
            if rc != 0:
                out["error_type"] = "auth_failed"
                out["error_message"] = (serr or sout)[-500:]

        elif action == "list-projects":
            rc, sout, serr = _run_zeabur(["project", "ls"], token, timeout=30)
            out["ok"] = (rc == 0)
            out["stdout_tail"] = sout[-3000:]

        elif action == "list-services":
            args = ["service", "ls"]
            if inputs.get("project_name"):
                args += ["--project-name", inputs["project_name"]]
            rc, sout, serr = _run_zeabur(args, token, timeout=60)
            out["ok"] = (rc == 0)
            out["stdout_tail"] = sout[-3000:]
            out["project"] = inputs.get("project_name", "")

        elif action == "deploy":
            args = ["deploy"]
            if inputs.get("project_name"):
                args += ["--project-name", inputs["project_name"]]
            if inputs.get("service_name"):
                args += ["--service-name", inputs["service_name"]]
            rc, sout, serr = _run_zeabur(args, token, timeout=timeout)
            out["ok"] = (rc == 0)
            out["stdout_tail"] = sout[-3000:]
            if rc != 0:
                out["stderr_tail"] = serr[-500:]
                out["error_type"] = "build_failed"
            # Try to extract URL from output
            url_match = re.search(r"https?://[\w\-./]+\.zeabur\.app[\w\-./]*", sout)
            if url_match:
                out["deployment_url"] = url_match.group(0)
            out["service"] = inputs.get("service_name", "")
            out["project"] = inputs.get("project_name", "")

        elif action == "logs":
            log_type = inputs.get("log_type", "runtime")
            args = ["deployment", "log", f"-t={log_type}"]
            if inputs.get("service_name"):
                args += ["--service-name", inputs["service_name"]]
            if inputs.get("env_id"):
                args += ["--env-id", inputs["env_id"]]
            rc, sout, serr = _run_zeabur(args, token, timeout=60)
            out["ok"] = (rc == 0)
            tail = int(inputs.get("tail_lines", 200))
            lines = sout.splitlines()
            out["stdout_tail"] = "\n".join(lines[-tail:])
            out["service"] = inputs.get("service_name", "")

        elif action == "status":
            args = ["deployment", "get"]
            if inputs.get("service_name"):
                args += ["--service-name", inputs["service_name"]]
            if inputs.get("env_id"):
                args += ["--env-id", inputs["env_id"]]
            rc, sout, serr = _run_zeabur(args, token, timeout=30)
            out["ok"] = (rc == 0)
            out["stdout_tail"] = sout[-2000:]
            out["service"] = inputs.get("service_name", "")

        elif action == "restart":
            args = ["service", "restart"]
            if inputs.get("service_name"):
                args += ["--service-name", inputs["service_name"]]
            if inputs.get("env_id"):
                args += ["--env-id", inputs["env_id"]]
            rc, sout, serr = _run_zeabur(args, token, timeout=60)
            out["ok"] = (rc == 0)
            out["stdout_tail"] = sout[-1000:]
            out["service"] = inputs.get("service_name", "")
        else:
            out = _err("unknown_action", action, action=action)

    except Exception as e:
        out = _err("unexpected", str(e)[:300], action=action)

    out["elapsed_ms"] = int((time.time() - t0) * 1000)
    print(json.dumps(out))
    sys.exit(0 if out.get("ok") else 1)


if __name__ == "__main__":
    main()

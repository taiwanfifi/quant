"""Sandbox execution. subprocess backend. Docker backend stub for future."""
from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


class SandboxBackendError(RuntimeError):
    pass


@dataclass
class ProcessResult:
    stdout: str
    stderr: str
    returncode: int
    duration_ms: int
    timed_out: bool
    backend: Literal["subprocess", "docker"]


# Allowlisted env vars passed through; everything else scrubbed
_DEFAULT_ENV_KEYS = {"PATH", "HOME", "LANG", "LC_ALL", "USER", "TMPDIR"}


def execute(
    cmd: list[str],
    *,
    timeout_s: int = 60,
    cwd: Path | str | None = None,
    env: dict | None = None,
    capture: bool = True,
    backend: Literal["subprocess", "docker"] = "subprocess",
    pass_env_keys: set[str] | None = None,
) -> ProcessResult:
    """
    Run cmd as subprocess; capture output.

    Args:
      cmd:           must be list[str], no shell=True
      timeout_s:     hard kill after this many seconds (clean SIGKILL)
      cwd:           working directory
      env:           dict to merge into scrubbed env; None = use defaults
      capture:       True captures stdout/stderr; False inherits (debug only)
      backend:       "subprocess" (default) or "docker" (not implemented)
      pass_env_keys: extra env keys from parent to pass through
    """
    if not cmd or not isinstance(cmd, list):
        raise ValueError("cmd must be a non-empty list of strings")

    if backend == "docker":
        raise SandboxBackendError("docker backend not yet implemented")
    if backend != "subprocess":
        raise SandboxBackendError(f"unknown backend: {backend}")

    # Build scrubbed env
    keys = set(_DEFAULT_ENV_KEYS)
    if pass_env_keys:
        keys |= set(pass_env_keys)
    scrubbed = {k: os.environ[k] for k in keys if k in os.environ}
    if env:
        scrubbed.update(env)

    cwd_str = str(cwd) if cwd else None

    t0 = time.time()
    timed_out = False
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd_str,
            env=scrubbed,
            shell=False,
            capture_output=capture,
            timeout=timeout_s,
        )
        stdout = proc.stdout.decode("utf-8", errors="replace") if capture else ""
        stderr = proc.stderr.decode("utf-8", errors="replace") if capture else ""
        rc = proc.returncode
    except subprocess.TimeoutExpired as e:
        timed_out = True
        stdout = (e.stdout.decode("utf-8", errors="replace")
                   if e.stdout else "")
        stderr = ((e.stderr.decode("utf-8", errors="replace") if e.stderr else "")
                   + f"\n[sandbox] timeout after {timeout_s}s")
        rc = -1
    except FileNotFoundError as e:
        raise SandboxBackendError(f"command not found: {cmd[0]} ({e})") from e

    return ProcessResult(
        stdout=stdout, stderr=stderr, returncode=rc,
        duration_ms=int((time.time() - t0) * 1000),
        timed_out=timed_out, backend="subprocess",
    )

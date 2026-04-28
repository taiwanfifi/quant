"""
Sandbox — controlled execution of external commands.

WHAT I DO:
  - Run a subprocess with timeout, capture stdout/stderr, return ProcessResult
  - Optional Docker backend (caller passes backend="docker" — not yet implemented)
  - Best-effort isolation: separate cwd, optional env scrubbing, no shell=True

WHAT I DON'T DO:
  - I don't currently spin up Docker (placeholder; subprocess is the only working backend)
  - I don't enforce CPU/memory limits at OS level (caller relies on timeout)
  - I don't sanitize input — caller passes cmd as list[str], no shell expansion

IO CONTRACT:
  execute(cmd: list[str], *, timeout_s: int, cwd: Path | None,
          env: dict | None, capture: bool = True) → ProcessResult
  ProcessResult(stdout, stderr, returncode, duration_ms, timed_out, backend)

HIDDEN FACTS:
  - shell=False always — caller must pass list, never string
  - Env defaults to a minimal scrubbed copy of parent env (PATH + HOME), not full
  - Timeout uses subprocess.run(timeout=...) which kills cleanly on Linux/macOS

DECOUPLING:
  - Pure stdlib (subprocess, os, time)
  - No imports from packages/*

For Task 1 we use subprocess backend. For untrusted repos in production, this is a
known compromise — the proper Docker backend lives behind a feature flag and will be
added when budget for Docker daemon on Zeabur is available.
"""

from .runner import execute, ProcessResult, SandboxBackendError

__all__ = ["execute", "ProcessResult", "SandboxBackendError"]

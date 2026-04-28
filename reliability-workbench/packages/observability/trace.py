"""JSONL trace recorder. Concurrency-safe via per-file lock."""
from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


TRACE_DIR = Path("_traces")

# Per-process file lock — multiple traces don't collide when calling _append.
# (multi-process safety relies on O_APPEND atomicity for small writes.)
_LOCK = threading.Lock()


def _sanitize(value: Any) -> Any:
    """Make a value JSON-safe. Recursively converts bytes/Path/etc. to str.
    Non-trivial fix per Gemini Round 1: data: dict, bytes/Path inside silently TypeError."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return f"<bytes len={len(value)}>"
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _sanitize(v) for k, v in value.items()}
    # Fallback: call str()
    try:
        return str(value)
    except Exception:
        return f"<unrepr {type(value).__name__}>"


@dataclass
class TraceContext:
    trace_id: str
    task: str
    started_at: float
    file_path: Path
    step_count: int = 0
    closed: bool = False
    metadata: dict = field(default_factory=dict)


def start(task: str, *, metadata: dict | None = None) -> TraceContext:
    TRACE_DIR.mkdir(exist_ok=True)
    ts_hex = format(int(time.time() * 1000), "x")
    rand = secrets.token_hex(3)
    # Sanitize task name for filesystem use: replace any non-[a-zA-Z0-9_-] with _
    safe_task = re.sub(r"[^a-zA-Z0-9_-]", "_", task)
    trace_id = f"tr_{safe_task}_{ts_hex}_{rand}"
    file_path = TRACE_DIR / f"{trace_id}.jsonl"
    ctx = TraceContext(
        trace_id=trace_id, task=task, started_at=time.time(),
        file_path=file_path, metadata=metadata or {},
    )
    _append(file_path, {
        "kind": "start", "trace_id": trace_id, "task": task,
        "started_at": ctx.started_at, "metadata": ctx.metadata,
    })
    return ctx


def step(ctx: TraceContext, kind: str, data: dict[str, Any]) -> None:
    if ctx.closed:
        raise RuntimeError(f"Trace {ctx.trace_id} already closed")
    ctx.step_count += 1
    _append(ctx.file_path, {
        "kind": kind, "step": ctx.step_count, "ts": time.time(),
        "elapsed_ms": int((time.time() - ctx.started_at) * 1000),
        **data,
    })


def end(ctx: TraceContext, *, output: dict | None = None, success: bool = True) -> str:
    if ctx.closed:
        return ctx.trace_id
    _append(ctx.file_path, {
        "kind": "end", "trace_id": ctx.trace_id,
        "elapsed_ms": int((time.time() - ctx.started_at) * 1000),
        "step_count": ctx.step_count, "success": success,
        "output": output,
    })
    ctx.closed = True
    return ctx.trace_id


def replay(trace_id: str) -> list[dict]:
    """Read back all events for a trace."""
    path = TRACE_DIR / f"{trace_id}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"No trace at {path}")
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _append(path: Path, event: dict):
    """Atomic-ish append. Recursively sanitize non-JSON data first (per Gemini critique).
    Open with O_APPEND + per-process lock for thread safety."""
    safe_event = _sanitize(event)
    line = json.dumps(safe_event, default=str, ensure_ascii=False) + "\n"
    encoded = line.encode("utf-8")
    with _LOCK:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, encoded)
        finally:
            os.close(fd)

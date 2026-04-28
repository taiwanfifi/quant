"""
Ollama (local) provider — fallback when API down or `require_local=True`.

Returns: (text, tokens_in, tokens_out, raw)

Assumes ollama is running at localhost:11434. If not available, raises RuntimeError —
caller (router) decides whether to fail or escalate.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any


OLLAMA_URL = "http://localhost:11434/api/chat"


def call(
    *,
    messages: list[dict],
    model: str,  # e.g., "ollama:llama3.3"
    temperature: float = 0,
    max_tokens: int = 4096,
    system: str | None = None,
) -> tuple[str, int, int, dict[str, Any]]:
    real_model = model.split(":", 1)[1] if ":" in model else "llama3.3"
    payload = {
        "model": real_model,
        "messages": messages if not system else [{"role": "system", "content": system}, *messages],
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(OLLAMA_URL, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            resp = json.loads(r.read())
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama not reachable at {OLLAMA_URL}: {e}") from e

    text = resp.get("message", {}).get("content", "")
    # Ollama returns prompt_eval_count and eval_count
    tokens_in = resp.get("prompt_eval_count", max(1, sum(len(m["content"]) for m in messages) // 4))
    tokens_out = resp.get("eval_count", max(1, len(text) // 4))
    return text, tokens_in, tokens_out, resp

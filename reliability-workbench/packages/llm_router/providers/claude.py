"""
Claude provider — uses Anthropic SDK with prompt caching enabled.

Returns: (text, tokens_in, tokens_out, raw_dict)
"""
from __future__ import annotations

import os
from typing import Any


def call(
    *,
    messages: list[dict],
    model: str,
    temperature: float = 0,
    max_tokens: int = 4096,
    system: str | None = None,
) -> tuple[str, int, int, dict[str, Any]]:
    try:
        from anthropic import Anthropic
    except ImportError as e:
        raise RuntimeError("anthropic SDK not installed; pip install anthropic") from e

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    # Map our model names to anthropic ones (we use suffix-less internally)
    model_map = {
        "claude-opus-4-7": "claude-opus-4-7",
        "claude-sonnet-4-6": "claude-sonnet-4-6",
        "claude-haiku-4-5": "claude-haiku-4-5",
    }
    anthropic_model = model_map.get(model, model)

    client = Anthropic(api_key=api_key)
    kwargs: dict[str, Any] = {
        "model": anthropic_model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if system:
        # Add cache_control to system for prompt caching (Anthropic feature)
        kwargs["system"] = [{"type": "text", "text": system,
                              "cache_control": {"type": "ephemeral"}}]

    resp = client.messages.create(**kwargs)
    text = "".join(b.text for b in resp.content if hasattr(b, "text"))
    raw = resp.model_dump() if hasattr(resp, "model_dump") else {}
    return text, resp.usage.input_tokens, resp.usage.output_tokens, raw

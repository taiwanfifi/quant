"""
Gemini provider — wraps the existing /Users/william/Downloads/python_c/gemini_helper.py
to reuse the proven curl_cffi + cookies session approach.

Returns: (text, tokens_in_estimate, tokens_out_estimate, raw_dict)

Notes:
  - Free (cookies-based, no API key)
  - No real token counts available; estimated from char_count / 4 (rough English heuristic)
  - cost is always 0.0
  - Cookies typically valid 1-2 months. When `RuntimeError("GET /app failed")` raises,
    treat as `CookieExpired` upstream.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# Prefer env var for cookies path, fall back to known location
_DEFAULT_COOKIES = "/Users/william/Downloads/python_c/cookies (19).txt"
COOKIES_FILE = os.environ.get("GEMINI_COOKIES_FILE", _DEFAULT_COOKIES)
HELPER_DIR = "/Users/william/Downloads/python_c"

# Module-level singleton session (cookies + token cached across calls)
_session = None


class CookieExpired(RuntimeError):
    pass


def _ensure_session():
    global _session
    if _session is not None:
        return _session
    if HELPER_DIR not in sys.path:
        sys.path.insert(0, HELPER_DIR)
    try:
        from gemini_helper import GeminiSession
    except ImportError as e:
        raise RuntimeError(
            f"Could not import gemini_helper from {HELPER_DIR}. "
            f"Either copy it here or fix path."
        ) from e
    _session = GeminiSession(cookies_file=COOKIES_FILE)
    return _session


def call(
    *,
    messages: list[dict],
    model: str = "gemini-3-flash",
    temperature: float = 0,
    max_tokens: int = 4096,
    system: str | None = None,
) -> tuple[str, int, int, dict[str, Any]]:
    """
    Convert messages list to a single prompt and send via cookies session.
    Multi-turn: re-uses GeminiSession's conv_id internally.
    """
    # Flatten messages (cookies session is single-prompt) — but it does have conv_id
    # for multi-turn continuity. For now, we send the last user message and rely on
    # session-level conv_id for context.
    if not messages:
        raise ValueError("messages cannot be empty")
    last = messages[-1]
    prompt = last["content"] if isinstance(last["content"], str) else str(last["content"])

    if system:
        prompt = f"[System: {system}]\n\n{prompt}"

    sess = _ensure_session()
    try:
        text = sess.chat(prompt, timeout=120)
    except RuntimeError as e:
        if "cookies" in str(e).lower() or "GET /app failed" in str(e):
            raise CookieExpired(str(e)) from e
        raise

    # Token estimates (no real count available)
    tokens_in = max(1, len(prompt) // 4)
    tokens_out = max(1, len(text) // 4)
    raw = {
        "conv_id": sess.conv_id,
        "resp_id": sess.resp_id,
        "choice_id": sess.choice_id,
    }
    return text, tokens_in, tokens_out, raw


def reset_session():
    """Force a fresh session (drop conversation context)."""
    global _session
    _session = None

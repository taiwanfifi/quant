"""
Gemini provider — self-contained curl_cffi + cookies session.

NOTE: was previously importing /Users/william/Downloads/python_c/gemini_helper.py;
that file went away when its parent dir was cleaned. This is now self-contained.

Returns: (text, tokens_in_estimate, tokens_out_estimate, raw_dict)

Notes:
  - Free (cookies-based, no API key)
  - No real token counts; estimated from char_count / 4 (rough English heuristic)
  - cost is always 0.0
  - Cookies typically valid 1-2 months. When 502 raises on /app, treat as CookieExpired.

Source: protocol details from Multi_Agent_Communication_指南.md (William 2026-04).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


_DEFAULT_COOKIES = "/Users/william/Downloads/python_c/cookies (19).txt"
COOKIES_FILE = os.environ.get("GEMINI_COOKIES_FILE", _DEFAULT_COOKIES)

_session_state = {
    "session": None,
    "token": None,
    "conv_id": None,
    "resp_id": None,
    "choice_id": None,
}


class CookieExpired(RuntimeError):
    pass


def _load_cookies(path: str = COOKIES_FILE,
                   target: str = "gemini.google.com") -> dict[str, str]:
    cookies: dict[str, str] = {}
    with open(path, "r", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            domain, _, _, _, _, name, value = parts[:7]
            d = domain.lstrip(".")
            if target.endswith(d):
                cookies[name] = value
    return cookies


def _parse_response(text: str) -> tuple[str | None, str | None, str | None, str | None]:
    """Parse Gemini StreamGenerate response. Returns (reply, conv_id, resp_id, choice_id)."""
    if text.startswith(")]}'"):
        text = text[4:]
    for line in text.strip().split("\n"):
        line = line.strip()
        if "wrb.fr" not in line:
            continue
        try:
            outer = json.loads(line)
            inner_str = outer[0][2]
            inner = json.loads(inner_str)
            conv_id = inner[1][0]
            resp_id = inner[1][1]
            choice_id = inner[4][0][0]
            reply = inner[4][0][1][0]
            return reply, conv_id, resp_id, choice_id
        except Exception:
            continue
    return None, None, None, None


def _ensure_session():
    """Lazy-init curl_cffi session, fetch CSRF token."""
    if _session_state["session"] is not None and _session_state["token"]:
        return _session_state["session"]

    try:
        from curl_cffi import requests as cffi_requests
    except ImportError as e:
        raise RuntimeError("curl_cffi not installed; pip install curl_cffi") from e

    cookies = _load_cookies()
    if not cookies:
        raise RuntimeError(f"no Google cookies loaded from {COOKIES_FILE}")
    sess = cffi_requests.Session(impersonate="chrome124")
    for k, v in cookies.items():
        sess.cookies.set(k, v, domain=".google.com")

    page = sess.get("https://gemini.google.com/app", timeout=15)
    if page.status_code != 200:
        raise CookieExpired(
            f"GET /app returned {page.status_code} — cookies likely expired. "
            f"Re-export from Chrome and update GEMINI_COOKIES_FILE."
        )

    # CSRF token; key has changed historically — try multiple
    token = None
    for key in ("WZsZ1e", "SNlM0e"):
        m = re.search(rf'"{key}":"(.*?)"', page.text)
        if m:
            token = m.group(1)
            break
    if not token:
        raise RuntimeError(
            "no CSRF token found (WZsZ1e/SNlM0e). Google may have changed the page."
        )

    _session_state["session"] = sess
    _session_state["token"] = token
    return sess


def call(
    *,
    messages: list[dict],
    model: str = "gemini-3-flash",
    temperature: float = 0,
    max_tokens: int = 4096,
    system: str | None = None,
) -> tuple[str, int, int, dict[str, Any]]:
    """
    LLMRouter-compatible interface. Sends last user message via cookies session.
    Multi-turn context preserved via module-level conv_id.
    """
    if not messages:
        raise ValueError("messages cannot be empty")
    last = messages[-1]
    prompt = last["content"] if isinstance(last["content"], str) else str(last["content"])
    if system:
        prompt = f"[System: {system}]\n\n{prompt}"

    sess = _ensure_session()
    token = _session_state["token"]

    if _session_state["conv_id"]:
        inner = [[prompt], None,
                 [_session_state["conv_id"],
                  _session_state["resp_id"],
                  _session_state["choice_id"]]]
    else:
        inner = [[prompt], None, None]

    resp = sess.post(
        "https://gemini.google.com/_/BardChatUi/data/assistant.lamda."
        "BardFrontendService/StreamGenerate",
        data={"f.req": json.dumps([None, json.dumps(inner)]), "at": token},
        headers={
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "Origin": "https://gemini.google.com",
            "Referer": "https://gemini.google.com/app",
        },
        timeout=180,
    )

    if resp.status_code == 502:
        raise CookieExpired(f"502 on StreamGenerate — cookies likely expired")

    text, c, r, ch = _parse_response(resp.text)

    # Only update IDs on parse success; failure preserves prior context
    if c: _session_state["conv_id"] = c
    if r: _session_state["resp_id"] = r
    if ch: _session_state["choice_id"] = ch

    if text is None:
        text = f"(parse error, response len={len(resp.text)})"

    tokens_in = max(1, len(prompt) // 4)
    tokens_out = max(1, len(text) // 4)
    raw = {
        "conv_id": _session_state["conv_id"],
        "resp_id": _session_state["resp_id"],
        "choice_id": _session_state["choice_id"],
    }
    return text, tokens_in, tokens_out, raw


def reset_session():
    """Drop conversation context (start fresh thread)."""
    _session_state["conv_id"] = None
    _session_state["resp_id"] = None
    _session_state["choice_id"] = None


# Convenience for ad-hoc scripts
def ask_gemini(prompt: str, *, system: str | None = None, timeout: int = 120) -> str:
    """Single-turn convenience function. Resets session each call."""
    reset_session()
    text, _, _, _ = call(
        messages=[{"role": "user", "content": prompt}],
        system=system,
    )
    return text


if __name__ == "__main__":
    import sys
    p = sys.stdin.read() if not sys.stdin.isatty() else " ".join(sys.argv[1:])
    print(ask_gemini(p))

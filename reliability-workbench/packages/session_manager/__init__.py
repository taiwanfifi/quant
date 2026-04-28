"""
Session Manager — HTTP sessions with cookies, rate limit, TLS impersonation.

WHAT I DO:
  - Open an HTTP session with optional cookies file (Netscape format)
  - Throttle to specified rate (e.g. SEC's 10 req/s)
  - Optional TLS fingerprint impersonation via curl_cffi (for cookie-protected sites)
  - GET / POST with consistent Response dataclass

WHAT I DON'T DO:
  - I don't parse content (use doc_parser)
  - I don't retry (caller wraps with backoff)
  - I don't know domain-specific rules (caller passes user_agent)
  - I don't manage cookie refresh (gemini cookies expire — caller detects)

IO CONTRACT:
  Session(cookies_file?, user_agent, rate_limit_rps, impersonate?)
  .get(url, timeout, max_bytes?) → Response
  .post(url, data, headers?, timeout) → Response

  Response(status, body, headers, elapsed_ms, url)

HIDDEN FACTS:
  - Rate limiter is per-Session instance (not global). Multiple Sessions can each tick at rate_limit_rps.
  - When `impersonate` is set, requires curl_cffi. If unavailable, falls back to urllib with warning.
  - Cookies are loaded once at __init__; not refreshed. If cookies expire, get/post will raise CookieExpired.
  - HTTP 4xx/5xx raise HTTPError (NOT swallowed — caller sees real status)
  - chunked read: if max_bytes set, stops after that many bytes (avoid OOM on huge responses)

DECOUPLING:
  - Optional dep: curl_cffi (for impersonation). Falls back to urllib if missing.
  - Doesn't import from packages/* at all.
  - Can be unit-tested with a local HTTP fixture.
"""

from .session import Session, Response, CookieExpired, RateLimitTriggered

__all__ = ["Session", "Response", "CookieExpired", "RateLimitTriggered"]

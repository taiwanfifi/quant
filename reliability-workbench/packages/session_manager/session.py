"""HTTP session with cookies, rate limit, optional TLS impersonation."""
from __future__ import annotations

import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib import error, parse, request


class CookieExpired(RuntimeError):
    """Raised when cookie auth fails (e.g. Gemini 502 on /app)."""


class RateLimitTriggered(Warning):
    """Emitted when rate limiter forced a sleep."""


@dataclass
class Response:
    status: int
    body: bytes
    headers: dict[str, str]
    elapsed_ms: int
    url: str                      # final URL after redirects


@dataclass
class _RateLimiter:
    rps: float
    last_call: float = 0.0

    @property
    def min_gap(self) -> float:
        return 1.0 / self.rps if self.rps > 0 else 0

    def wait(self):
        gap = time.time() - self.last_call
        if gap < self.min_gap:
            sleep_s = self.min_gap - gap
            if sleep_s > 0.05:  # only warn for noticeable sleeps
                warnings.warn(f"rate-limited: sleeping {sleep_s:.3f}s",
                              RateLimitTriggered, stacklevel=3)
            time.sleep(sleep_s)
        self.last_call = time.time()


class Session:
    def __init__(
        self,
        *,
        cookies_file: Path | str | None = None,
        user_agent: str = "ReliabilityWorkbench/0.1",
        rate_limit_rps: float = 10.0,
        impersonate: str | None = None,
        cookies_target_domain: str | None = None,
    ):
        self.user_agent = user_agent
        self._limiter = _RateLimiter(rps=rate_limit_rps)
        self._cookies = self._load_cookies(cookies_file, cookies_target_domain) if cookies_file else {}
        self._impl = self._init_impl(impersonate)

    # ---------- impl selection ----------
    def _init_impl(self, impersonate: str | None):
        if impersonate is None:
            return ("urllib", None)
        try:
            from curl_cffi import requests as cffi_requests  # type: ignore
            sess = cffi_requests.Session(impersonate=impersonate)
            for k, v in self._cookies.items():
                sess.cookies.set(k, v, domain=".google.com")  # generic
            return ("curl_cffi", sess)
        except ImportError:
            warnings.warn(f"curl_cffi not installed; impersonate={impersonate} ignored",
                          UserWarning)
            return ("urllib", None)

    # ---------- cookies (Netscape format) ----------
    @staticmethod
    def _load_cookies(path: Path | str, target_domain: str | None) -> dict[str, str]:
        cookies: dict[str, str] = {}
        with open(path, errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 7:
                    continue
                domain, _, _, _, _, name, value = parts[:7]
                d = domain.lstrip(".")
                if target_domain is None or target_domain.endswith(d):
                    cookies[name] = value
        return cookies

    # ---------- public API ----------
    def get(self, url: str, *, timeout: float = 30,
            max_bytes: int | None = None) -> Response:
        self._limiter.wait()
        if self._impl[0] == "curl_cffi":
            return self._cffi_get(url, timeout, max_bytes)
        return self._urllib_get(url, timeout, max_bytes)

    def post(self, url: str, *, data: dict | bytes,
             headers: dict | None = None, timeout: float = 30) -> Response:
        self._limiter.wait()
        if self._impl[0] == "curl_cffi":
            return self._cffi_post(url, data, headers, timeout)
        return self._urllib_post(url, data, headers, timeout)

    # ---------- urllib backend ----------
    def _build_headers(self, extra: dict | None = None) -> dict:
        h = {"User-Agent": self.user_agent}
        if self._cookies:
            h["Cookie"] = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
        if extra:
            h.update(extra)
        return h

    def _urllib_get(self, url: str, timeout: float,
                    max_bytes: int | None) -> Response:
        req = request.Request(url, headers=self._build_headers())
        t0 = time.time()
        try:
            with request.urlopen(req, timeout=timeout) as r:
                return self._read_response(r, t0, max_bytes)
        except error.HTTPError as e:
            # 502 from gemini.google.com/app typically = cookies expired
            if e.code == 502 and "gemini.google.com" in url:
                raise CookieExpired(f"502 on {url} — cookies likely expired") from e
            raise

    def _urllib_post(self, url: str, data: dict | bytes,
                     extra_headers: dict | None, timeout: float) -> Response:
        if isinstance(data, dict):
            body = parse.urlencode(data).encode()
            ct = "application/x-www-form-urlencoded"
        else:
            body = data
            ct = "application/octet-stream"
        headers = self._build_headers({"Content-Type": ct, **(extra_headers or {})})
        req = request.Request(url, data=body, headers=headers, method="POST")
        t0 = time.time()
        with request.urlopen(req, timeout=timeout) as r:
            return self._read_response(r, t0, max_bytes=None)

    def _read_response(self, r: Any, t0: float,
                       max_bytes: int | None) -> Response:
        if max_bytes is not None:
            chunks, total = [], 0
            while True:
                chunk = r.read(min(1024 * 1024, max_bytes - total))
                if not chunk: break
                chunks.append(chunk); total += len(chunk)
                if total >= max_bytes: break
            body = b"".join(chunks)
        else:
            body = r.read()
        return Response(
            status=getattr(r, "status", 200),
            body=body,
            headers=dict(r.headers.items()),
            elapsed_ms=int((time.time() - t0) * 1000),
            url=r.url if hasattr(r, "url") else "",
        )

    # ---------- curl_cffi backend ----------
    def _cffi_get(self, url: str, timeout: float,
                  max_bytes: int | None) -> Response:
        t0 = time.time()
        sess = self._impl[1]
        r = sess.get(url, timeout=timeout, headers={"User-Agent": self.user_agent})
        body = r.content
        if max_bytes is not None and len(body) > max_bytes:
            body = body[:max_bytes]
        if r.status_code == 502 and "gemini.google.com" in url:
            raise CookieExpired(f"502 on {url} via curl_cffi — cookies likely expired")
        return Response(
            status=r.status_code, body=body,
            headers=dict(r.headers), elapsed_ms=int((time.time() - t0) * 1000),
            url=str(r.url),
        )

    def _cffi_post(self, url: str, data: dict | bytes,
                   extra_headers: dict | None, timeout: float) -> Response:
        t0 = time.time()
        sess = self._impl[1]
        headers = {"User-Agent": self.user_agent, **(extra_headers or {})}
        r = sess.post(url, data=data, headers=headers, timeout=timeout)
        return Response(
            status=r.status_code, body=r.content,
            headers=dict(r.headers), elapsed_ms=int((time.time() - t0) * 1000),
            url=str(r.url),
        )

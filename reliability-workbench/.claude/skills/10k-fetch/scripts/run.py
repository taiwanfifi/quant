#!/usr/bin/env python3
"""
10k-fetch — read JSON from stdin, fetch SEC 10-K, write JSON to stdout.

Usage:
  echo '{"cik":"0000320193","accession":"0000320193-25-000079"}' | python run.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

# Resolve packages dir relative to this skill (3 dirs up: scripts/ → 10k-fetch/ → skills/ → .claude/ → repo root)
REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from packages.session_manager import Session  # noqa: E402
from packages.doc_parser import detect_format  # noqa: E402

CACHE_ROOT = REPO_ROOT / "_cache" / "sec_filings"


def _emit_error(error_type: str, error_message: str, exit_code: int = 1):
    """Emit error JSON to stdout per output_schema, then exit."""
    out = {
        "ok": False,
        "filing_dir": "",
        "primary_doc_path": "",
        "raw_hash": "sha256:" + ("0" * 64),
        "size_bytes": 0,
        "format_hint": "html",
        "fetched_at": time.time(),
        "from_cache": False,
        "error_type": error_type,
        "error_message": error_message,
    }
    print(json.dumps(out))
    sys.exit(exit_code)


def _user_agent() -> str:
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua:
        # Fallback that's still SEC-compliant per their policy
        ua = "ReliabilityWorkbench/0.1 contact@example.com"
    return ua


def _make_session() -> Session:
    return Session(
        user_agent=_user_agent(),
        rate_limit_rps=9.0,  # under SEC's 10 rps cap
    )


def _hash_bytes(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


def fetch_via_accession(cik: str, accession: str, *,
                        force_refresh: bool, max_size_mb: int) -> dict:
    """Look up primary doc via submissions API, then download."""
    sess = _make_session()
    cik_int = int(cik)
    cache_dir = CACHE_ROOT / cik / accession
    meta_path = cache_dir / "fetch_meta.json"

    # Cache hit?
    if not force_refresh and meta_path.exists():
        try:
            cached = json.loads(meta_path.read_text())
            primary_path = Path(cached["primary_doc_path"])
            if primary_path.exists():
                # Verify integrity
                actual_hash = _hash_bytes(primary_path.read_bytes())
                if actual_hash == cached.get("raw_hash"):
                    cached["from_cache"] = True
                    cached["fetched_at"] = time.time()
                    return cached
        except Exception:
            pass  # fall through to re-fetch

    # 1. Get submissions to find primary doc
    sub_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        resp = sess.get(sub_url, timeout=30)
    except Exception as e:
        return _err("network_timeout", f"submissions API: {e}")

    if resp.status != 200:
        return _err("submissions_api_error", f"HTTP {resp.status}")

    try:
        sub = json.loads(resp.body)
    except json.JSONDecodeError as e:
        return _err("submissions_api_error", f"bad JSON: {e}")

    # Find accession in recent OR older chunks
    primary = None
    rec = sub.get("filings", {}).get("recent", {})
    for i, acc in enumerate(rec.get("accessionNumber", [])):
        if acc == accession:
            primary = rec["primaryDocument"][i]
            break

    if primary is None:
        # Search older files
        for f in sub.get("filings", {}).get("files", []):
            chunk_url = f"https://data.sec.gov/submissions/{f['name']}"
            try:
                cresp = sess.get(chunk_url, timeout=30)
                chunk = json.loads(cresp.body)
                for i, acc in enumerate(chunk.get("accessionNumber", [])):
                    if acc == accession:
                        primary = chunk["primaryDocument"][i]
                        break
                if primary:
                    break
            except Exception:
                continue

    if primary is None:
        return _err("accession_not_found",
                    f"accession {accession} not found in submissions for CIK {cik}")

    # 1990s historical filings often have empty primaryDocument in submissions API.
    # Fall back to <accession>.txt convention (the canonical full submission text).
    if not primary or not primary.strip():
        primary = f"{accession}.txt"

    # 2. Build URL and download
    acc_clean = accession.replace("-", "")
    primary_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{primary}"
    max_bytes = max_size_mb * 1024 * 1024

    try:
        resp = sess.get(primary_url, timeout=300, max_bytes=max_bytes)
    except Exception as e:
        return _err("network_timeout", f"primary doc fetch: {e}")

    if resp.status != 200:
        return _err("primary_fetch_error", f"HTTP {resp.status}")

    content = resp.body
    if len(content) >= max_bytes:
        return _err("oversize",
                    f"filing >= {max_size_mb} MB (got {len(content)/1e6:.1f} MB)")

    # 3. Save + meta
    cache_dir.mkdir(parents=True, exist_ok=True)
    primary_path = cache_dir / primary
    primary_path.write_bytes(content)
    raw_hash = _hash_bytes(content)
    fmt = detect_format(content)

    out = {
        "ok": True,
        "filing_dir": str(cache_dir),
        "primary_doc_path": str(primary_path),
        "primary_doc_url": primary_url,
        "raw_hash": raw_hash,
        "size_bytes": len(content),
        "format_hint": fmt,
        "fetched_at": time.time(),
        "from_cache": False,
        "fetch_strategy": "submissions-api+primary",
    }
    meta_path.write_text(json.dumps(out, indent=2))
    return out


def fetch_via_url(file_url: str, *, force_refresh: bool, max_size_mb: int) -> dict:
    sess = _make_session()
    parsed = urlparse(file_url)
    if parsed.netloc != "www.sec.gov" or "/Archives/edgar/data/" not in parsed.path:
        return _err("bad_url", f"only www.sec.gov/Archives/edgar/data/ URLs allowed")

    # Cache by URL hash
    url_hash = hashlib.sha1(file_url.encode()).hexdigest()[:16]
    cache_dir = CACHE_ROOT / "by-url" / url_hash
    primary_name = Path(parsed.path).name
    primary_path = cache_dir / primary_name

    if not force_refresh and primary_path.exists():
        content = primary_path.read_bytes()
        return {
            "ok": True, "filing_dir": str(cache_dir),
            "primary_doc_path": str(primary_path), "primary_doc_url": file_url,
            "raw_hash": _hash_bytes(content), "size_bytes": len(content),
            "format_hint": detect_format(content),
            "fetched_at": time.time(), "from_cache": True,
            "fetch_strategy": "by-url-cached",
        }

    max_bytes = max_size_mb * 1024 * 1024
    try:
        resp = sess.get(file_url, timeout=300, max_bytes=max_bytes)
    except Exception as e:
        return _err("network_timeout", f"by-url fetch: {e}")

    if resp.status != 200:
        return _err("primary_fetch_error", f"HTTP {resp.status}")
    content = resp.body
    if len(content) >= max_bytes:
        return _err("oversize", f"file >= {max_size_mb} MB")

    cache_dir.mkdir(parents=True, exist_ok=True)
    primary_path.write_bytes(content)

    return {
        "ok": True, "filing_dir": str(cache_dir),
        "primary_doc_path": str(primary_path), "primary_doc_url": file_url,
        "raw_hash": _hash_bytes(content), "size_bytes": len(content),
        "format_hint": detect_format(content),
        "fetched_at": time.time(), "from_cache": False,
        "fetch_strategy": "by-url-fresh",
    }


def _err(error_type: str, error_message: str) -> dict:
    return {
        "ok": False, "filing_dir": "", "primary_doc_path": "",
        "raw_hash": "sha256:" + ("0" * 64), "size_bytes": 0,
        "format_hint": "html", "fetched_at": time.time(),
        "from_cache": False,
        "error_type": error_type, "error_message": error_message,
    }


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        _emit_error("input_empty", "no JSON on stdin")
    try:
        inputs = json.loads(raw)
    except json.JSONDecodeError as e:
        _emit_error("input_invalid_json", str(e))

    force_refresh = bool(inputs.get("force_refresh", False))
    max_size_mb = int(inputs.get("max_size_mb", 50))

    if "file_url" in inputs:
        out = fetch_via_url(inputs["file_url"],
                            force_refresh=force_refresh,
                            max_size_mb=max_size_mb)
    elif "cik" in inputs and "accession" in inputs:
        out = fetch_via_accession(inputs["cik"], inputs["accession"],
                                   force_refresh=force_refresh,
                                   max_size_mb=max_size_mb)
    else:
        _emit_error("input_missing_fields",
                    "must provide either file_url OR (cik + accession)")

    print(json.dumps(out))
    sys.exit(0 if out.get("ok") else 1)


if __name__ == "__main__":
    main()

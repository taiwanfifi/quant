#!/usr/bin/env python3
"""
10k-resolve-incorporation — find and extract Proxy section corresponding to a 10-K item.

Strategy: regex-first section detection → LLM fallback if regex misses.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from packages.session_manager import Session  # noqa: E402
from packages.doc_parser import parse, ParseError  # noqa: E402
from packages.llm_router.providers import gemini_cookies  # noqa: E402


# Known DEF 14A section headers per item (regex patterns; case-insensitive)
ITEM_SECTION_PATTERNS = {
    "10": [
        r"\bElection\s+of\s+Directors\b",
        r"\bDirectors\s+and\s+Executive\s+Officers\b",
        r"\bCorporate\s+Governance\b",
        r"\bBoard\s+of\s+Directors\b",
    ],
    "11": [
        r"\bExecutive\s+Compensation\b",
        r"\bCompensation\s+Discussion\s+and\s+Analysis\b",
        r"\bCD&A\b",
        r"\bDirector\s+Compensation\b",
    ],
    "12": [
        r"\bSecurity\s+Ownership\b",
        r"\bBeneficial\s+Ownership\b",
        r"\bPrincipal\s+Stockholders\b",
        r"\bEquity\s+Compensation\s+Plan\b",
    ],
    "13": [
        r"\bRelated\s+Person\s+Transactions\b",
        r"\bRelated\s+Party\s+Transactions\b",
        r"\bDirector\s+Independence\b",
        r"\bCertain\s+Relationships\b",
    ],
    "14": [
        r"\bPrincipal\s+Accountant\s+Fees\b",
        r"\bAudit\s+Fees\b",
        r"\bIndependent\s+Auditor\b",
    ],
}


def _err(error_type: str, error_message: str) -> dict:
    return {
        "ok": False, "resolved": False, "elapsed_ms": 0,
        "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
        "fallback_chain": [],
        "error_type": error_type, "error_message": error_message,
    }


def _user_agent() -> str:
    return os.environ.get("SEC_USER_AGENT",
                           "ReliabilityWorkbench/0.1 contact@example.com")


def find_def14a(cik: str, filing_date: str | None,
                  search_window_months: int) -> dict | None:
    """Find most recent DEF 14A within window. Returns submission entry or None."""
    sess = Session(user_agent=_user_agent(), rate_limit_rps=9.0)
    try:
        resp = sess.get(f"https://data.sec.gov/submissions/CIK{cik}.json", timeout=30)
    except Exception:
        return None
    if resp.status != 200:
        return None
    sub = json.loads(resp.body)

    # Window
    if filing_date:
        try:
            target = datetime.strptime(filing_date[:10], "%Y-%m-%d")
            earliest = target - timedelta(days=30 * search_window_months)
            latest = target + timedelta(days=180)  # Proxy often filed BEFORE 10-K
        except ValueError:
            target = None; earliest = None; latest = None
    else:
        target = None; earliest = None; latest = None

    rec = sub.get("filings", {}).get("recent", {})
    matches = []
    for i, form in enumerate(rec.get("form", [])):
        if form != "DEF 14A":
            continue
        date = rec["filingDate"][i]
        try:
            d = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            continue
        if earliest and d < earliest:
            continue
        if latest and d > latest:
            continue
        matches.append({
            "form_type": "DEF 14A",
            "filed_at": date,                   # consistent with 10k-fetch output
            "accession": rec["accessionNumber"][i],
            "primary_doc": rec["primaryDocument"][i],
            "date_obj": d,
        })

    if not matches:
        return None
    # Pick closest to filing_date (or most recent if no target)
    if target:
        matches.sort(key=lambda m: abs((m["date_obj"] - target).days))
    else:
        matches.sort(key=lambda m: m["date_obj"], reverse=True)
    best = matches[0]
    best.pop("date_obj", None)
    return best


def fetch_def14a(cik: str, accession: str, primary_doc: str) -> bytes | None:
    sess = Session(user_agent=_user_agent(), rate_limit_rps=9.0)
    cik_int = int(cik)
    acc_clean = accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{primary_doc}"
    try:
        resp = sess.get(url, timeout=180, max_bytes=50 * 1024 * 1024)
    except Exception:
        return None
    return resp.body if resp.status == 200 else None


def find_section_regex(plaintext: str, item_number: str) -> tuple[int, int, str] | None:
    """Returns (start, end, matched_title) or None."""
    patterns = ITEM_SECTION_PATTERNS.get(item_number, [])
    if not patterns:
        return None
    best = None  # (start, score, matched_text)
    for pat in patterns:
        for m in re.finditer(pat, plaintext, re.IGNORECASE):
            # Prefer matches that look like headings (preceded by punctuation/newline)
            ctx_before = plaintext[max(0, m.start() - 50):m.start()]
            score = 1.0
            if re.search(r"[\n\r]\s*$", ctx_before) or m.group(0).isupper():
                score = 2.0
            if best is None or score > best[1]:
                best = (m.start(), score, m.group(0))
    if best is None:
        return None
    start = best[0]
    # End: next major section header (any other ITEM pattern, or 8000 chars later)
    next_section_re = re.compile(
        r"\b(?:Election\s+of\s+Directors|Executive\s+Compensation|"
        r"Security\s+Ownership|Beneficial\s+Ownership|"
        r"Related\s+Person\s+Transactions|Principal\s+Accountant\s+Fees|"
        r"Compensation\s+Discussion|Audit\s+Fees|"
        r"Director\s+Compensation|Equity\s+Compensation\s+Plan)\b",
        re.IGNORECASE,
    )
    next_match = None
    for m in next_section_re.finditer(plaintext, start + 100):
        if m.group(0).lower() != best[2].lower():
            next_match = m
            break
    end = next_match.start() if next_match else min(len(plaintext), start + 12000)
    return start, end, best[2]


def find_section_llm(plaintext: str, item_number: str, item_title: str) -> tuple[int, int, str] | None:
    """LLM fallback: ask which section corresponds to the item. Returns char range."""
    snippet = plaintext[:60000]  # cap context
    prompt = f"""You are reading a SEC DEF 14A Proxy Statement.

Find the section that corresponds to "Item {item_number}: {item_title}" of the company's 10-K (which incorporates this Proxy by reference).

Common Item-to-Section mappings:
- Item 10 → Election of Directors / Corporate Governance / Directors and Executive Officers
- Item 11 → Executive Compensation / Compensation Discussion and Analysis
- Item 12 → Security Ownership / Beneficial Ownership
- Item 13 → Related Person Transactions / Director Independence
- Item 14 → Principal Accountant Fees / Audit Fees

Proxy plaintext (first 60K chars):
---
{snippet}
---

Return ONLY a JSON object:
{{
  "found": true | false,
  "section_title": "the section header you identified",
  "approx_start_char": 12345,
  "approx_end_char": 23456,
  "evidence_quote": "first 100 chars of the section"
}}

If you can't find the section, return {{"found": false}}."""
    try:
        text, tin, tout, _raw = gemini_cookies.call(
            messages=[{"role": "user", "content": prompt}],
            model="gemini-3-flash", temperature=0,
        )
    except Exception:
        return None
    # Parse JSON
    if "```" in text:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not data.get("found"):
        return None
    start = int(data.get("approx_start_char", 0))
    end = int(data.get("approx_end_char", start + 8000))
    title = data.get("section_title", f"Item {item_number} content")
    return start, min(end, len(plaintext)), title


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps(_err("input_empty", "no JSON on stdin")))
        sys.exit(1)
    try:
        inputs = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps(_err("input_invalid_json", str(e))))
        sys.exit(1)

    t0 = time.time()
    cik = inputs["cik"]
    item_number = str(inputs["item_number"]).upper()
    item_title = inputs.get("item_title", f"Item {item_number}")
    filing_date = inputs.get("filing_date")
    window = int(inputs.get("search_window_months", 18))

    fallback_chain: list[str] = []

    # 1. Find DEF 14A
    def14a = find_def14a(cik, filing_date, window)
    if def14a is None:
        out = _err("no_def14a_within_window",
                    f"no DEF 14A within ±{window}mo of {filing_date}")
        out["resolved"] = False
        out["elapsed_ms"] = int((time.time() - t0) * 1000)
        print(json.dumps(out))
        sys.exit(0)  # not a hard failure — caller may proceed

    # 2. Fetch Proxy
    proxy_bytes = fetch_def14a(cik, def14a["accession"], def14a["primary_doc"])
    if proxy_bytes is None:
        out = _err("proxy_fetch_failed", f"could not fetch {def14a['accession']}")
        out["resolved"] = False
        out["source_doc"] = def14a
        out["elapsed_ms"] = int((time.time() - t0) * 1000)
        print(json.dumps(out))
        sys.exit(0)

    # 3. Parse to plaintext
    try:
        doc = parse(proxy_bytes, max_file_size_mb=100)
    except ParseError as e:
        out = _err("parse_failed", str(e))
        out["resolved"] = False
        out["source_doc"] = def14a
        out["elapsed_ms"] = int((time.time() - t0) * 1000)
        print(json.dumps(out))
        sys.exit(0)

    # 4. Find section: regex first
    fallback_chain.append("regex")
    section = find_section_regex(doc.plaintext, item_number)
    extraction_method = "regex_section_header" if section else None
    confidence = 0.85

    # 5. LLM fallback if regex missed
    tokens_in = tokens_out = 0
    if section is None:
        fallback_chain.append("llm")
        section = find_section_llm(doc.plaintext, item_number, item_title)
        if section is not None:
            extraction_method = "llm_section_locate"
            confidence = 0.70

    if section is None:
        out = {
            "ok": True, "resolved": False,
            "reason": "section_not_found",
            "source_doc": def14a,
            "content_text": None,
            "content_text_preview": "",
            "confidence": 0.0,
            "elapsed_ms": int((time.time() - t0) * 1000),
            "tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": 0.0,
            "fallback_chain": fallback_chain,
        }
        print(json.dumps(out))
        sys.exit(0)

    start, end, title = section
    content_text = doc.plaintext[start:end].strip()
    content_text = re.sub(r"\s+", " ", content_text)

    out = {
        "ok": True,
        "resolved": True,
        "source_doc": def14a,
        "section_found": {
            "title_matched": title,
            "char_range": [start, end],
            "extraction_method": extraction_method,
        },
        "content_text": content_text[:50000],  # cap output size
        "content_text_preview": content_text[:200],
        "confidence": confidence,
        "elapsed_ms": int((time.time() - t0) * 1000),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": 0.0,
        "fallback_chain": fallback_chain,
    }
    print(json.dumps(out))
    sys.exit(0)


if __name__ == "__main__":
    main()

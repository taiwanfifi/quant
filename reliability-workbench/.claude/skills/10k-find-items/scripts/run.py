#!/usr/bin/env python3
"""
10k-find-items — Tier A rules-based candidate finder.

Input (stdin JSON):  {"filing_path": "/abs/path"} OR {"raw_bytes_b64": "..."}
Output (stdout JSON): see ../assets/output_schema.json
"""
from __future__ import annotations

import base64
import json
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from packages.doc_parser import parse, ParseError, FileTooLargeError  # noqa: E402


# ──────────────────────────────────────────
# Regex patterns (tiered by confidence)
# ──────────────────────────────────────────

PART_RE = re.compile(r"\bPART\s+(I{1,3}V?|IV)\b", re.IGNORECASE)

# Confidence-tiered Item patterns. Order matters: first-match wins per position.
ITEM_PATTERNS = [
    # 0.95: standard with dot (e.g. "Item 1A.", "ITEM 1.")
    (re.compile(r"\b(Item|ITEM)\s+(\d{1,2}[A-Z]?)\.\s+([A-Z])"), 0.95, "standard-with-dot"),
    # 0.80: standard without dot but capitalized (e.g. "Item 1A Risk Factors")
    (re.compile(r"\b(Item)\s+(\d{1,2}[A-Z]?)\s+[A-Z][a-z]+"), 0.80, "standard-no-dot"),
    # 0.65: ALL CAPS heading (typical of 1990s plaintext)
    (re.compile(r"\bITEM\s+(\d{1,2}[A-Z]?)\s+[A-Z]{2,}"), 0.65, "all-caps-heading"),
    # 0.40: just "Item N" anywhere — could be cross-reference
    (re.compile(r"\b(Item|ITEM)\s+(\d{1,2}[A-Z]?)\b"), 0.40, "any-mention"),
]

INCORP_RE = re.compile(r"incorporated\s+(?:herein\s+)?by\s+reference", re.IGNORECASE)
RESERVED_RE = re.compile(r"\bItem\s+\d+\.?\s*[Rr]eserved\b")
# Note: amendment detection moved to doc_parser (Document.metadata.form_type) — was
# previously a regex here that produced false positives. Skills should not own
# format-detection logic; that belongs in the parser layer. See feedback 2026-04-26.


def _err(error_type: str, error_message: str) -> dict:
    return {
        "ok": False, "format": "unknown", "items": [],
        "items_unique_count": 0, "parts_unique": [],
        "rules_confidence": 0.0, "needs_llm_fallback": True,
        "fallback_reason": error_message,
        "elapsed_ms": 0,
        "error_type": error_type, "error_message": error_message,
    }


def find_items(plaintext: str) -> list[dict]:
    """Apply tiered patterns. Returns dedup'd candidates by item_number (first-position wins)."""
    raw_matches: dict[str, dict] = {}  # item_number → first match info
    for pattern, conf, label in ITEM_PATTERNS:
        for m in pattern.finditer(plaintext):
            # Last group containing item number — patterns differ
            groups = m.groups()
            number = next((g for g in reversed(groups)
                            if g and re.fullmatch(r"\d{1,2}[A-Z]?", g.upper())), None)
            if number is None:
                continue
            number = number.upper()
            # Keep the FIRST occurrence with HIGHEST confidence per item_number
            if number not in raw_matches:
                raw_matches[number] = {
                    "item_number": number,
                    "char_offset": m.start(),
                    "matched_text": m.group(0)[:80],
                    "confidence": conf,
                    "pattern_used": label,
                }
            else:
                # Prefer higher confidence at any position
                if conf > raw_matches[number]["confidence"]:
                    raw_matches[number] = {
                        "item_number": number,
                        "char_offset": m.start(),
                        "matched_text": m.group(0)[:80],
                        "confidence": conf,
                        "pattern_used": label,
                    }
    # Sort by char_offset (document order)
    return sorted(raw_matches.values(), key=lambda x: x["char_offset"])


def find_parts(plaintext: str) -> tuple[list[str], int]:
    matches = list(PART_RE.finditer(plaintext))
    return sorted(set(m.group(1).upper() for m in matches)), len(matches)


def compute_rules_confidence(parts: list[str], items: list[dict],
                              signals: dict) -> tuple[float, str | None]:
    """5-signal aggregate per SKILL.md spec. Returns (confidence, fallback_reason)."""
    score = 0.0
    reasons = []

    # 1. parts_unique == 4? (0.25)
    if len(parts) == 4:
        score += 0.25
    elif len(parts) >= 1:
        score += 0.10
        reasons.append(f"parts_unique={len(parts)} (expected 4)")
    else:
        reasons.append("no PART found")

    # 2. items_unique_count >= 14? (0.25)
    n = len(items)
    if n >= 14:
        score += 0.25
    elif n >= 7:
        score += 0.10
        reasons.append(f"items_unique={n} (low for normal 10-K)")
    else:
        reasons.append(f"items_unique={n} (very low)")

    # 3. Standard pattern dominates? (0.20)
    if items:
        n_std = sum(1 for it in items if it["pattern_used"].startswith("standard"))
        if n_std / len(items) >= 0.8:
            score += 0.20
        elif n_std / len(items) >= 0.5:
            score += 0.10
            reasons.append("mixed pattern strength")
        else:
            reasons.append("most matches are weak patterns")

    # 4. Continuous numbering? (0.15)
    if items:
        nums_int = []
        for it in items:
            try:
                nums_int.append(int(re.match(r"\d+", it["item_number"]).group()))
            except (AttributeError, ValueError):
                continue
        if nums_int:
            unique_ints = sorted(set(nums_int))
            # Heuristic: should span 1..max_int with no big gaps
            expected_max = max(unique_ints)
            actual_count = len(unique_ints)
            if actual_count >= expected_max * 0.7:
                score += 0.15
            else:
                score += 0.05
                reasons.append(f"sparse numbering: {actual_count}/{expected_max}")

    # 5. No envelope-strip warnings (0.15)
    if not signals.get("html_entity_quirks") and not signals.get("is_amendment_indicator"):
        score += 0.15
    elif signals.get("is_amendment_indicator"):
        reasons.append("amendment detected (10-K/A)")
    elif signals.get("html_entity_quirks"):
        reasons.append("HTML entity quirks remain")

    return min(1.0, max(0.0, score)), "; ".join(reasons) if reasons else None


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

    # Get bytes
    if "filing_path" in inputs:
        path = Path(inputs["filing_path"])
        if not path.exists():
            print(json.dumps(_err("file_not_found", str(path))))
            sys.exit(1)
        content = path.read_bytes()
    elif "raw_bytes_b64" in inputs:
        try:
            content = base64.b64decode(inputs["raw_bytes_b64"])
        except Exception as e:
            print(json.dumps(_err("invalid_b64", str(e))))
            sys.exit(1)
    else:
        print(json.dumps(_err("missing_input", "need filing_path or raw_bytes_b64")))
        sys.exit(1)

    # Parse
    try:
        doc = parse(content, max_file_size_mb=100)
    except FileTooLargeError as e:
        print(json.dumps(_err("oversize", str(e))))
        sys.exit(1)
    except ParseError as e:
        print(json.dumps(_err("parse_failed", str(e))))
        sys.exit(1)

    # Run rules
    parts_unique, parts_raw = find_parts(doc.plaintext)
    items = find_items(doc.plaintext)

    # Signals — form type comes from parser layer (authoritative)
    is_amendment = bool(doc.metadata.form_type and doc.metadata.form_type.endswith("/A"))
    signals = {
        "incorporated_by_reference_count": len(INCORP_RE.findall(doc.plaintext)),
        "reserved_count": len(RESERVED_RE.findall(doc.plaintext)),
        "is_amendment_indicator": is_amendment,
        "form_type": doc.metadata.form_type,
        "form_type_source": doc.metadata.form_type_source,
        "envelope_type": "pem-sgml-1990s" if doc.format == "pem-sgml" else "modern",
        "html_entity_quirks": ("&#" in doc.plaintext or "&nbsp;" in doc.plaintext),
    }

    confidence, fallback_reason = compute_rules_confidence(parts_unique, items, signals)
    needs_fallback = confidence < 0.7

    out = {
        "ok": True,
        "format": doc.format,
        "extraction_strategy": doc.extraction_strategy,
        "plaintext_chars": len(doc.plaintext),
        "raw_hash": "sha256:" + doc.raw_hash,
        "parts_unique": parts_unique,
        "parts_raw_match_count": parts_raw,
        "items": items,
        "items_unique_count": len(items),
        "signals": signals,
        "rules_confidence": round(confidence, 3),
        "needs_llm_fallback": needs_fallback,
        "fallback_reason": fallback_reason,
        "elapsed_ms": int((time.time() - t0) * 1000),
    }

    print(json.dumps(out))
    sys.exit(0)


if __name__ == "__main__":
    main()

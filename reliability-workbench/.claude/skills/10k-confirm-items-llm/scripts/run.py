#!/usr/bin/env python3
"""
10k-confirm-items-llm — Tier B LLM confirmation.

Strategy: single-prompt-per-filing. Send TOC + first 80K chars + rules candidates.
LLM returns structured items with status classification.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from packages.doc_parser import parse  # noqa: E402
from packages.llm_router.providers import gemini_cookies  # noqa: E402


PROMPT_TEMPLATE = """You are a SEC 10-K filing structural classifier.

You will be given:
  1. The filing's plaintext (clipped to {max_chars} chars)
  2. The form_type (10-K, 10-K/A, etc.)
  3. Rules-based item candidates that a regex layer found (with per-candidate confidence)

Your job: produce the AUTHORITATIVE list of items present in this filing, with status classification.

# Status classification rules

For each item identified, classify into ONE of:

- `extracted`: The item's actual content text appears in this filing (substantive paragraphs)
- `incorporated_by_reference`: The filing says "[content] is incorporated herein by reference to ..." pointing OUTSIDE this filing (commonly to DEF 14A Proxy)
- `not_applicable`: Filing explicitly says "Not Applicable" or "N/A" or omits content because the item doesn't apply to this registrant
- `reserved`: Filing labels item as "Reserved" (SEC has deprecated/repurposed the slot — Item 6 commonly reserved post-2021)

# Edge cases

- A 10-K/A amendment may only update SOME items. List items that are TOUCHED by the amendment as `extracted`; rest as `not_applicable` for THIS filing.
- If form_type is NOT 10-K or 10-K/A (e.g., the candidate filing is actually an exhibit), return empty items list with a warning.
- If you can't tell whether content is in-line or referenced, prefer `incorporated_by_reference` (conservative).
- Item titles: use the SEC-standard title where you can identify it (e.g., "Risk Factors" for 1A, "Properties" for 2). If the filing uses a non-standard title, keep yours STANDARD (mark `provenance.title_inferred=true`).

# Output JSON schema (STRICT)

```json
{{
  "items": [
    {{
      "part": "I" | "II" | "III" | "IV",
      "item_number": "1" | "1A" | "1B" | "1C" | "2" | ... | "16",
      "item_title": "Risk Factors",
      "char_offset_hint": 12345 | null,
      "status": "extracted" | "incorporated_by_reference" | "not_applicable" | "reserved",
      "content_text_preview": "first 150 chars of actual content, or empty for non-extracted",
      "confidence": 0.0-1.0,
      "provenance": {{
        "rules_candidate_used": true,
        "title_inferred": false,
        "ambiguity_note": null
      }}
    }}
  ],
  "warnings": []
}}
```

Return ONLY the JSON object. No prose before or after.

---

# Form type: {form_type}

# Rules candidates (from regex layer, char_offset is byte position in plaintext):
{rules_candidates}

# Plaintext (clipped to {max_chars} chars):

{plaintext}
"""


def _err(error_type: str, error_message: str) -> dict:
    return {
        "ok": False, "items": [], "items_total": 0,
        "status_distribution": {}, "model_used": "",
        "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
        "elapsed_ms": 0, "fallback_chain": [],
        "error_type": error_type, "error_message": error_message,
    }


def call_gemini(prompt: str) -> tuple[str, int, int]:
    text, tin, tout, _raw = gemini_cookies.call(
        messages=[{"role": "user", "content": prompt}],
        model="gemini-3-flash", temperature=0,
    )
    return text, tin, tout


def call_claude(prompt: str, model: str) -> tuple[str, int, int]:
    """Lazy-load claude provider so absence of API key doesn't break gemini path."""
    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    from packages.llm_router.providers import claude
    text, tin, tout, _raw = claude.call(
        messages=[{"role": "user", "content": prompt}],
        model=model, temperature=0, max_tokens=8000,
    )
    return text, tin, tout


def parse_llm_json(text: str) -> dict | None:
    """Extract JSON from LLM output. Tolerates markdown fence and surrounding prose."""
    # Strip markdown fence
    if "```" in text:
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
    # Find outermost {...}
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def classify_part(item_number: str) -> str:
    """Map item_number to part. SEC standard mapping."""
    num_match = re.match(r"(\d+)", item_number)
    if not num_match:
        return "I"
    n = int(num_match.group(1))
    if 1 <= n <= 4:
        return "I"
    elif 5 <= n <= 9:
        return "II"
    elif 10 <= n <= 14:
        return "III"
    elif 15 <= n <= 16:
        return "IV"
    return "I"


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
    filing_path = inputs["filing_path"]
    rules_out = inputs.get("rules_output") or {}
    max_chars = int(inputs.get("max_chars_to_llm", 80000))
    deadline = inputs.get("absolute_deadline_unix")
    model_pref = inputs.get("model_preference", "auto")

    if deadline is not None and time.time() > deadline:
        print(json.dumps(_err("deadline_exceeded", "before LLM call")))
        sys.exit(1)

    # 1. Get plaintext
    try:
        content = Path(filing_path).read_bytes()
        doc = parse(content, max_file_size_mb=100)
    except FileNotFoundError as e:
        print(json.dumps(_err("file_not_found", str(e))))
        sys.exit(1)
    except Exception as e:
        print(json.dumps(_err("parse_failed", str(e))))
        sys.exit(1)

    plaintext = doc.plaintext[:max_chars]
    truncated = len(doc.plaintext) > max_chars
    form_type = (doc.metadata.form_type
                 or rules_out.get("signals", {}).get("form_type")
                 or "10-K")

    # 2. Build rules candidates summary
    rules_candidates = rules_out.get("items", [])
    if not rules_candidates:
        rules_candidates_str = "(no rules candidates — running cold)"
    else:
        rules_candidates_str = json.dumps(
            [{"item_number": it["item_number"],
              "char_offset": it.get("char_offset"),
              "confidence": it.get("confidence"),
              "pattern": it.get("pattern_used"),
              "matched": it.get("matched_text", "")[:60]}
             for it in rules_candidates],
            indent=2,
        )

    prompt = PROMPT_TEMPLATE.format(
        form_type=form_type,
        rules_candidates=rules_candidates_str,
        plaintext=plaintext,
        max_chars=max_chars,
    )

    # 3. Pick model + call
    fallback_chain = []
    text = None
    model_used = ""
    tokens_in = tokens_out = 0
    cost_usd = 0.0
    last_error = None

    candidates = []
    if model_pref in ("auto", "claude"):
        candidates.extend(["claude-sonnet-4-6", "claude-haiku-4-5"])
    if model_pref in ("auto", "gemini"):
        candidates.append("gemini-3-flash")
    if model_pref.startswith(("claude", "gemini")) and model_pref not in candidates:
        candidates.insert(0, model_pref)

    for cand in candidates:
        try:
            if cand.startswith("claude"):
                text, tokens_in, tokens_out = call_claude(prompt, cand)
                model_used = cand
                cost_usd = (tokens_in * 3.0 + tokens_out * 15.0) / 1_000_000 if "sonnet" in cand else \
                           (tokens_in * 0.8 + tokens_out * 4.0) / 1_000_000
            elif cand.startswith("gemini"):
                text, tokens_in, tokens_out = call_gemini(prompt)
                model_used = cand
                cost_usd = 0.0
            fallback_chain.append(cand)
            break
        except Exception as e:
            fallback_chain.append(f"{cand}:{type(e).__name__}")
            last_error = str(e)
            continue

    if text is None:
        out = _err("llm_unreachable", f"all candidates failed; last={last_error}")
        out["fallback_chain"] = fallback_chain
        print(json.dumps(out))
        sys.exit(1)

    # 4. Parse JSON
    parsed = parse_llm_json(text)
    if parsed is None:
        # One retry with stricter instruction
        retry_prompt = (prompt
                        + "\n\nIMPORTANT: Your last response was not parseable JSON. "
                          "Return ONLY a JSON object, no prose, no markdown fences.")
        try:
            if model_used.startswith("claude"):
                text2, tokens_in2, tokens_out2 = call_claude(retry_prompt, model_used)
            else:
                text2, tokens_in2, tokens_out2 = call_gemini(retry_prompt)
            parsed = parse_llm_json(text2)
            tokens_in += tokens_in2
            tokens_out += tokens_out2
            fallback_chain.append(f"{model_used}:retry")
        except Exception:
            pass

    if parsed is None:
        out = _err("output_unparseable", f"LLM output not JSON; preview={text[:300]}")
        out["model_used"] = model_used
        out["tokens_in"] = tokens_in
        out["tokens_out"] = tokens_out
        out["cost_usd"] = cost_usd
        out["fallback_chain"] = fallback_chain
        out["elapsed_ms"] = int((time.time() - t0) * 1000)
        print(json.dumps(out))
        sys.exit(1)

    # 5. Normalize items
    items_raw = parsed.get("items", [])
    items: list = []
    distribution: dict = {"extracted": 0, "incorporated_by_reference": 0,
                           "not_applicable": 0, "reserved": 0}
    for it in items_raw:
        item_number = str(it.get("item_number", "")).upper().strip()
        if not item_number:
            continue
        part = it.get("part") or classify_part(item_number)
        status = it.get("status", "extracted")
        if status not in distribution:
            status = "extracted"  # fallback for unexpected values
        distribution[status] += 1

        items.append({
            "part": part,
            "item_number": item_number,
            "item_title": it.get("item_title", ""),
            "char_offset": it.get("char_offset_hint"),
            "char_range_estimated": None,  # filled by 10k-assemble
            "status": status,
            "content_text_preview": it.get("content_text_preview", "")[:200],
            "confidence": float(it.get("confidence", 0.7)),
            "provenance": it.get("provenance") or {
                "rules_candidate_used": True,
                "title_inferred": False,
                "ambiguity_note": None,
            },
        })

    warnings = parsed.get("warnings", []) or []
    if truncated:
        warnings.append(f"plaintext truncated from {len(doc.plaintext)} to {max_chars} chars")

    out = {
        "ok": True,
        "items": items,
        "items_total": len(items),
        "status_distribution": distribution,
        "model_used": model_used,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": round(cost_usd, 4),
        "elapsed_ms": int((time.time() - t0) * 1000),
        "fallback_chain": fallback_chain,
        "warnings": warnings,
    }
    print(json.dumps(out))
    sys.exit(0)


if __name__ == "__main__":
    main()

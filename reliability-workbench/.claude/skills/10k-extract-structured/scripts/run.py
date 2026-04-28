#!/usr/bin/env python3
"""
10k-extract-structured — orchestrator skill for end-to-end 10-K extraction.

Runs:
  1. 10k-fetch
  2. 10k-find-items (Tier A rules)
  3. 10k-confirm-items-llm (Tier B, conditional)
  4. 10k-resolve-incorporation (per-item, for incorporated items)
  5. Assemble final spec-compliant JSON
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from packages.observability import start as trace_start, step as trace_step, end as trace_end  # noqa: E402

SKILLS_DIR = REPO_ROOT / ".claude" / "skills"


def _err(error_type: str, error_message: str, stages: list | None = None) -> dict:
    return {
        "ok": False,
        "filing": {}, "items": [],
        "summary": {"total_cost_usd": 0.0, "total_elapsed_ms": 0,
                     "items_total": 0, "status_distribution": {}},
        "stages": stages or [],
        "error_type": error_type, "error_message": error_message,
    }


def _run_skill(name: str, inputs: dict, timeout: int = 600) -> dict:
    """Run a sub-skill via subprocess. Returns the parsed JSON output."""
    run_py = SKILLS_DIR / name / "scripts" / "run.py"
    if not run_py.exists():
        return {"ok": False, "_error": f"sub-skill {name} not found"}
    proc = subprocess.run(
        [sys.executable, str(run_py)],
        input=json.dumps(inputs).encode(),
        capture_output=True, timeout=timeout,
    )
    if proc.returncode != 0:
        try:
            return {"ok": False, "_error": json.loads(proc.stdout)}
        except Exception:
            return {"ok": False, "_error": f"exit {proc.returncode}: {proc.stderr.decode()[:300]}"}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "_error": f"sub-skill {name} returned non-JSON"}


# Standard SEC item titles (used as fallback when LLM doesn't provide one)
STANDARD_TITLES = {
    "1": "Business",
    "1A": "Risk Factors",
    "1B": "Unresolved Staff Comments",
    "1C": "Cybersecurity",
    "2": "Properties",
    "3": "Legal Proceedings",
    "4": "Mine Safety Disclosures",
    "5": "Market for Registrant's Common Equity, Related Stockholder Matters and Issuer Purchases of Equity Securities",
    "6": "Reserved",
    "7": "Management's Discussion and Analysis of Financial Condition and Results of Operations",
    "7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Financial Statements and Supplementary Data",
    "9": "Changes in and Disagreements With Accountants on Accounting and Financial Disclosure",
    "9A": "Controls and Procedures",
    "9B": "Other Information",
    "9C": "Disclosure Regarding Foreign Jurisdictions That Prevent Inspections",
    "10": "Directors, Executive Officers and Corporate Governance",
    "11": "Executive Compensation",
    "12": "Security Ownership of Certain Beneficial Owners and Management and Related Stockholder Matters",
    "13": "Certain Relationships and Related Transactions, and Director Independence",
    "14": "Principal Accountant Fees and Services",
    "15": "Exhibit and Financial Statement Schedules",
    "16": "Form 10-K Summary",
}


def _classify_part(item_number: str) -> str:
    m = re.match(r"(\d+)", item_number)
    if not m:
        return "I"
    n = int(m.group(1))
    if 1 <= n <= 4: return "I"
    if 5 <= n <= 9: return "II"
    if 10 <= n <= 14: return "III"
    if 15 <= n <= 16: return "IV"
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
    cik = inputs.get("cik", "")
    accession = inputs.get("accession", "")
    always_run_llm = bool(inputs.get("always_run_llm", False))
    resolve_ibr = bool(inputs.get("resolve_incorporation", True))
    max_chars = int(inputs.get("max_chars_to_llm", 80000))
    model_pref = inputs.get("model_preference", "auto")
    deadline = inputs.get("absolute_deadline_unix")

    case_label = f"{cik}_{accession}" if cik else "url-input"
    ctx = trace_start(task=f"10k_extract_{case_label}",
                      metadata={"inputs": {k: v for k, v in inputs.items()
                                            if k != "absolute_deadline_unix"}})

    stages: list = []
    total_cost = 0.0

    # ─── Stage 1: fetch ───
    fetch_input = {k: v for k, v in inputs.items()
                    if k in ("cik", "accession", "file_url", "force_refresh", "max_size_mb")}
    fetch_out = _run_skill("10k-fetch", fetch_input)
    stages.append({"stage": "fetch", "duration_ms": 0,
                    "from_cache": fetch_out.get("from_cache"),
                    "ok": fetch_out.get("ok", False)})
    trace_step(ctx, kind="skill", data={"skill": "10k-fetch", **stages[-1]})

    if not fetch_out.get("ok"):
        out = _err("fetch_failed", json.dumps(fetch_out.get("_error") or fetch_out)[:300], stages)
        trace_end(ctx, output={"failed_at": "fetch"}, success=False)
        print(json.dumps(out))
        sys.exit(1)

    primary_doc_path = fetch_out["primary_doc_path"]
    filing = {
        "cik": cik or fetch_out.get("primary_doc_url", ""),
        "accession": accession,
        "form_type": "10-K",  # refined in next stage
        "filed_at": "",
        "primary_doc": Path(primary_doc_path).name,
        "raw_hash": fetch_out["raw_hash"],
        "primary_doc_url": fetch_out.get("primary_doc_url", ""),
    }

    # ─── Stage 2: find-items (Tier A) ───
    s2_t = time.time()
    find_out = _run_skill("10k-find-items", {"filing_path": primary_doc_path})
    s2_dur = int((time.time() - s2_t) * 1000)
    if not find_out.get("ok"):
        out = _err("find_items_failed", json.dumps(find_out.get("_error") or find_out)[:300], stages)
        trace_end(ctx, output={"failed_at": "find-items"}, success=False)
        print(json.dumps(out))
        sys.exit(1)

    rules_conf = find_out.get("rules_confidence", 0.0)
    needs_llm = find_out.get("needs_llm_fallback", True)
    form_type = find_out.get("signals", {}).get("form_type")
    if form_type:
        filing["form_type"] = form_type
    stages.append({
        "stage": "find-items", "duration_ms": s2_dur,
        "items_found": find_out.get("items_unique_count", 0),
        "rules_confidence": rules_conf,
        "needs_llm_fallback": needs_llm,
    })
    trace_step(ctx, kind="skill", data={"skill": "10k-find-items", **stages[-1]})

    # ─── Stage 3: LLM Tier B (conditional) ───
    run_llm = always_run_llm or needs_llm or rules_conf < 0.7
    confirm_out: dict = {}
    if run_llm:
        s3_t = time.time()
        confirm_out = _run_skill("10k-confirm-items-llm", {
            "filing_path": primary_doc_path,
            "rules_output": find_out,
            "model_preference": model_pref,
            "max_chars_to_llm": max_chars,
            "absolute_deadline_unix": deadline,
        }, timeout=300)
        s3_dur = int((time.time() - s3_t) * 1000)
        cost = float(confirm_out.get("cost_usd", 0.0))
        total_cost += cost
        stages.append({
            "stage": "confirm-llm", "duration_ms": s3_dur,
            "skipped": False,
            "model_used": confirm_out.get("model_used", ""),
            "cost_usd": cost,
            "items_returned": confirm_out.get("items_total", 0),
            "status_distribution": confirm_out.get("status_distribution", {}),
        })
        trace_step(ctx, kind="skill", data={"skill": "10k-confirm-items-llm", **stages[-1]})
    else:
        stages.append({"stage": "confirm-llm", "duration_ms": 0, "skipped": True,
                        "reason": "rules_confidence_sufficient"})

    # ─── Decide source of truth for items ───
    # If LLM ran successfully, prefer LLM items (they have status). Otherwise build from rules.
    if confirm_out.get("ok"):
        items_source = confirm_out["items"]
        tier_used_default = "rules+llm"
    else:
        # Build minimal items from rules only — no status info, mark as extracted by default
        items_source = []
        for it in find_out.get("items", []):
            items_source.append({
                "part": _classify_part(it["item_number"]),
                "item_number": it["item_number"],
                "item_title": STANDARD_TITLES.get(it["item_number"], ""),
                "char_offset": it.get("char_offset"),
                "char_range_estimated": None,
                "status": "extracted",
                "content_text_preview": it.get("matched_text", "")[:80],
                "confidence": it.get("confidence", 0.5),
                "provenance": {"strategy": "rules-only",
                                "rules_candidate_used": True,
                                "title_inferred": True},
            })
        tier_used_default = "rules"

    # ─── Stage 4: resolve incorporation (per-item for IBR) ───
    ibr_resolved_count = 0
    ibr_unresolved_count = 0
    if resolve_ibr:
        s4_t = time.time()
        for item in items_source:
            if item.get("status") != "incorporated_by_reference":
                continue
            if not cik:
                continue  # can't resolve without CIK
            res_out = _run_skill("10k-resolve-incorporation", {
                "cik": cik,
                "item_number": item["item_number"],
                "item_title": item.get("item_title", ""),
                "filing_date": filing.get("filed_at", ""),
            }, timeout=300)
            if res_out.get("ok") and res_out.get("resolved"):
                item["content_text"] = res_out.get("content_text") or ""
                item["content_text_preview"] = res_out.get("content_text_preview", "")
                item["confidence"] = max(item.get("confidence", 0), res_out.get("confidence", 0))
                item["provenance"] = {
                    **(item.get("provenance") or {}),
                    "tier_used": "ibr-deep-follow",
                    "source_doc": res_out.get("source_doc"),
                    "extraction_method": res_out.get("section_found", {}).get("extraction_method"),
                    "section_title_matched": res_out.get("section_found", {}).get("title_matched"),
                }
                ibr_resolved_count += 1
            else:
                item["provenance"] = {
                    **(item.get("provenance") or {}),
                    "tier_used": "ibr-unresolved",
                    "ibr_failure_reason": res_out.get("reason", "unknown"),
                }
                ibr_unresolved_count += 1
        s4_dur = int((time.time() - s4_t) * 1000)
        stages.append({
            "stage": "resolve-ibr", "duration_ms": s4_dur,
            "resolved_count": ibr_resolved_count,
            "unresolved_count": ibr_unresolved_count,
        })
        trace_step(ctx, kind="skill", data={"skill": "10k-resolve-incorporation",
                                              **stages[-1]})

    # ─── Stage 5: assemble final spec-compliant items ───
    final_items = []
    distribution = {"extracted": 0, "incorporated_by_reference": 0,
                     "not_applicable": 0, "reserved": 0}
    tier_dist = {"rules": 0, "rules+llm": 0, "ibr-deep-follow": 0, "ibr-unresolved": 0}

    for item in items_source:
        item_num = item["item_number"]
        # Override item_title with SEC standard if missing or generic
        title = item.get("item_title") or STANDARD_TITLES.get(item_num, "")
        if not title:
            title = f"Item {item_num}"

        char_range = item.get("char_range_estimated")
        if char_range is None and item.get("char_offset") is not None:
            char_range = [item["char_offset"], item["char_offset"] + 1000]

        status = item.get("status", "extracted")
        if status not in distribution:
            status = "extracted"
        distribution[status] += 1

        prov = item.get("provenance") or {}
        tier = prov.get("tier_used", tier_used_default)
        if tier in tier_dist:
            tier_dist[tier] += 1

        final_items.append({
            "part": item.get("part") or _classify_part(item_num),
            "item_number": item_num,
            "item_title": title,
            "content_text": item.get("content_text") or item.get("content_text_preview") or "",
            "char_range": char_range,
            "status": status,
            "confidence": round(float(item.get("confidence", 0.7)), 3),
            "provenance": prov,
        })

    summary = {
        "items_total": len(final_items),
        "status_distribution": distribution,
        "incorporated_resolved": ibr_resolved_count,
        "incorporated_unresolved": ibr_unresolved_count,
        "total_cost_usd": round(total_cost, 4),
        "total_elapsed_ms": int((time.time() - t0) * 1000),
        "tier_distribution": tier_dist,
    }

    out = {
        "ok": True,
        "trace_id": ctx.trace_id,
        "filing": filing,
        "items": final_items,
        "summary": summary,
        "stages": stages,
    }
    trace_end(ctx, output={"items_total": len(final_items),
                              "cost_usd": total_cost}, success=True)
    print(json.dumps(out))
    sys.exit(0)


if __name__ == "__main__":
    main()

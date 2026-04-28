#!/usr/bin/env python3
"""
End-to-end pipeline demo using current Skills.

Pipeline stages currently implemented:
  Stage 1: 10k-fetch              → fetch primary doc from SEC
  Stage 2: 10k-find-items (Tier A) → rules-based candidates + confidence
  [Stage 3-N: LLM Tier B + status classify + assemble — NOT YET BUILT]

Records trace + cost + structured output. Runs on AAPL 2025 + 3 contrast cases.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from packages.skills_registry import SkillsRegistry, ExecutionResult
from packages.observability import start as trace_start, step as trace_step, end as trace_end
from packages.cost_ledger import CostLedger

os.environ.setdefault("SEC_USER_AGENT",
                      "ReliabilityWorkbench/0.1 taiwanfifi@gmail.com")


CASES = [
    {
        "label": "AAPL 2025",
        "tag":   "modern-healthy",
        "input": {"cik": "0000320193", "accession": "0000320193-25-000079"},
    },
    {
        "label": "PFE 2026",
        "tag":   "modern-html-quirks",
        "input": {"cik": "0000078003", "accession": "0000078003-26-000003",
                  "force_refresh": False},
        # Skip-fetch: we already have the file from sandbox
        "skip_fetch_use_path": "/Users/william/Downloads/quant/_datasets/sec_10k_seed/PFE/2026/pfe-20251231.htm",
    },
    {
        "label": "Ford 1995",
        "tag":   "pem-sgml-old",
        "skip_fetch_use_path": "/Users/william/Downloads/quant/_datasets/sec_10k_old/F/1995/0000950124-95-000729.txt",
    },
    {
        "label": "JPM 10-K/A 1999",
        "tag":   "amendment-only-exhibit",
        "skip_fetch_use_path": "/Users/william/Downloads/quant/_datasets/sec_10k_old/JPM/1999/0000950123-99-006055.txt",
    },
]


def run_one_case(sr: SkillsRegistry, ledger: CostLedger, case: dict) -> dict:
    """Pipeline a single filing. Returns flat result dict."""
    label = case["label"]
    ctx = trace_start(task=f"sec10k_pipeline_{label.replace(' ', '_')}",
                      metadata={"case_tag": case["tag"]})

    result: dict = {
        "label": label, "tag": case["tag"],
        "stages": [], "total_elapsed_ms": 0, "total_cost_usd": 0.0,
        "trace_id": ctx.trace_id,
    }

    t_pipeline = time.time()

    # ─── Stage 1: fetch (or use pre-existing path) ───
    s1_t0 = time.time()
    if "skip_fetch_use_path" in case:
        primary_doc_path = case["skip_fetch_use_path"]
        s1_out = {
            "ok": True,
            "primary_doc_path": primary_doc_path,
            "size_bytes": Path(primary_doc_path).stat().st_size,
            "format_hint": "(detected at next stage)",
            "from_cache": True, "fetch_strategy": "pre-existing-local",
        }
        s1_validated = True
        s1_dur = int((time.time() - s1_t0) * 1000)
    else:
        try:
            r1: ExecutionResult = sr.execute("10k-fetch", case["input"])
            s1_out = r1.output
            s1_validated = r1.validated
            s1_dur = r1.duration_ms
            primary_doc_path = s1_out["primary_doc_path"] if s1_out.get("ok") else None
        except Exception as e:
            trace_step(ctx, kind="error", data={"stage": 1, "error": str(e)})
            trace_end(ctx, output={"failed_at": "stage_1"}, success=False)
            return {**result, "error": f"stage_1_fetch: {e}"}

    trace_step(ctx, kind="skill", data={
        "stage": 1, "skill": "10k-fetch",
        "duration_ms": s1_dur,
        "validated": s1_validated,
        "from_cache": s1_out.get("from_cache"),
        "size_bytes": s1_out.get("size_bytes"),
        "format_hint": s1_out.get("format_hint"),
    })
    result["stages"].append({
        "n": 1, "skill": "10k-fetch",
        "duration_ms": s1_dur, "validated": s1_validated,
        "key_outputs": {
            "primary_doc_path": primary_doc_path,
            "size_bytes": s1_out.get("size_bytes"),
            "format_hint": s1_out.get("format_hint"),
            "raw_hash": s1_out.get("raw_hash", "")[:24] + "...",
            "from_cache": s1_out.get("from_cache"),
        },
    })

    if primary_doc_path is None:
        trace_end(ctx, output={"failed_at": "stage_1"}, success=False)
        return result

    # ─── Stage 2: find-items (Tier A rules) ───
    s2_t0 = time.time()
    try:
        r2: ExecutionResult = sr.execute("10k-find-items",
                                         {"filing_path": primary_doc_path})
        s2_out = r2.output
        s2_validated = r2.validated
        s2_dur = r2.duration_ms
    except Exception as e:
        trace_step(ctx, kind="error", data={"stage": 2, "error": str(e)})
        trace_end(ctx, output={"failed_at": "stage_2"}, success=False)
        return {**result, "error": f"stage_2_find_items: {e}"}

    trace_step(ctx, kind="skill", data={
        "stage": 2, "skill": "10k-find-items",
        "duration_ms": s2_dur,
        "validated": s2_validated,
        "format": s2_out.get("format"),
        "items_unique_count": s2_out.get("items_unique_count"),
        "rules_confidence": s2_out.get("rules_confidence"),
        "needs_llm_fallback": s2_out.get("needs_llm_fallback"),
    })
    result["stages"].append({
        "n": 2, "skill": "10k-find-items",
        "duration_ms": s2_dur, "validated": s2_validated,
        "key_outputs": {
            "format": s2_out.get("format"),
            "extraction_strategy": s2_out.get("extraction_strategy"),
            "plaintext_chars": s2_out.get("plaintext_chars"),
            "parts_unique": s2_out.get("parts_unique"),
            "items_unique_count": s2_out.get("items_unique_count"),
            "items_sample": [it["item_number"] for it in (s2_out.get("items") or [])[:6]],
            "rules_confidence": s2_out.get("rules_confidence"),
            "needs_llm_fallback": s2_out.get("needs_llm_fallback"),
            "fallback_reason": s2_out.get("fallback_reason"),
            "signals": s2_out.get("signals"),
        },
    })

    # ─── Decision: would Tier B kick in? ───
    decision = "rules-sufficient" if not s2_out.get("needs_llm_fallback") else "would-escalate-to-llm"
    trace_step(ctx, kind="decision", data={
        "decision": decision,
        "rules_confidence": s2_out.get("rules_confidence"),
        "threshold": 0.7,
    })
    result["decision"] = decision
    result["rules_confidence"] = s2_out.get("rules_confidence")

    # ─── (Future) Stage 3-N: Tier B + classify-status + xbrl-cross-val + assemble ───
    not_yet_built = ["10k-confirm-items-llm", "10k-classify-status", "10k-cross-validate-xbrl", "10k-assemble"]
    result["not_yet_built"] = not_yet_built
    for s in not_yet_built:
        trace_step(ctx, kind="planned", data={"skill": s, "note": "not yet built"})

    # Finalize
    result["total_elapsed_ms"] = int((time.time() - t_pipeline) * 1000)
    result["total_cost_usd"] = 0.0  # rules only; no LLM yet
    trace_end(ctx, output={
        "stages_completed": len(result["stages"]),
        "decision": decision,
    }, success=True)
    return result


def main():
    sr = SkillsRegistry(skills_dir=str(REPO_ROOT / ".claude" / "skills"))
    ledger = CostLedger(db_path=str(REPO_ROOT / "_cache" / "demo_ledger.db"))

    print("=" * 78)
    print(" Reliability Workbench — Pipeline Demo (Stage 1+2 of N)")
    print(" " + time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 78)
    print()
    skills = [s.name for s in sr.list_all()]
    print(f" Skills loaded:        {skills}")
    print(f" Pipeline stages:      [10k-fetch] → [10k-find-items] → [...future]")
    print()

    all_results = []
    for case in CASES:
        print(f"┌─ Running: {case['label']} ({case['tag']})")
        r = run_one_case(sr, ledger, case)
        all_results.append(r)
        if "error" in r:
            print(f"│  ✗ ERROR: {r['error']}")
            print()
            continue
        for stage in r["stages"]:
            print(f"│  Stage {stage['n']} {stage['skill']}: "
                  f"{stage['duration_ms']:>4}ms, validated={stage['validated']}")
            for k, v in stage["key_outputs"].items():
                if isinstance(v, dict):
                    v = json.dumps(v, separators=(",", ":"))
                if isinstance(v, list):
                    v = str(v)
                if v is not None and len(str(v)) > 80:
                    v = str(v)[:77] + "..."
                print(f"│     {k}: {v}")
        print(f"│  → decision: {r.get('decision')} (confidence={r.get('rules_confidence')})")
        print(f"│  → total: {r['total_elapsed_ms']}ms, cost=${r['total_cost_usd']:.4f}")
        print(f"│  → trace: {r['trace_id']}")
        print(f"│  → not yet built (would run next): {r.get('not_yet_built')}")
        print(f"└─")
        print()

    # Aggregate
    print("=" * 78)
    print(" Summary")
    print("=" * 78)
    print(f"{'Case':<25} {'Format':<10} {'Items':<6} {'Conf':<6} {'Decision':<25} {'ms':<5}")
    print("-" * 78)
    for r in all_results:
        if "error" in r:
            print(f"{r['label']:<25} ERROR: {r['error']}")
            continue
        s2 = next((s for s in r["stages"] if s["n"] == 2), None)
        if not s2:
            continue
        ko = s2["key_outputs"]
        print(f"{r['label']:<25} {ko.get('format', '?'):<10} "
              f"{ko.get('items_unique_count', 0):<6} "
              f"{ko.get('rules_confidence', 0):<6} "
              f"{r.get('decision', '?'):<25} "
              f"{r['total_elapsed_ms']:<5}")

    # Save full JSON
    out_path = REPO_ROOT / "_sandbox" / "demo_pipeline_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(all_results, indent=2, default=str))
    print()
    print(f" Full JSON: {out_path}")
    print(f" Traces:    {REPO_ROOT}/_traces/")


if __name__ == "__main__":
    main()

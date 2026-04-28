#!/usr/bin/env python3
"""
Run the SEC 10-K extraction eval suite.

Usage:
  python apps/sec10k-extractor/run_eval.py [--suite golden] [--rules-only] [--max-cases N]
  python apps/sec10k-extractor/run_eval.py --suite golden --max-cases 4

Output: prints per-case + summary; writes report to apps/sec10k-extractor/evals/reports/
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("SEC_USER_AGENT", "ReliabilityWorkbench/0.1 taiwanfifi@gmail.com")

from packages.eval_kit import EvalKit, InvariantScorer, StructuralScorer
from packages.skills_registry import SkillsRegistry


SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
EVAL_DIR = REPO_ROOT / "apps" / "sec10k-extractor" / "evals"
REPORTS_DIR = EVAL_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def make_runner(rules_only: bool):
    """Build a runner closure that calls 10k-extract-structured per case."""
    sr = SkillsRegistry(skills_dir=str(SKILLS_DIR))

    def runner(case_input: dict) -> dict:
        skill_inputs = dict(case_input)
        skill_inputs["always_run_llm"] = not rules_only
        skill_inputs["resolve_incorporation"] = not rules_only
        skill_inputs["model_preference"] = "gemini"

        if rules_only:
            # Just stage 1 + 2 (fetch + find-items), no LLM, no IBR
            t0 = time.time()
            r1 = sr.execute("10k-fetch", {k: v for k, v in skill_inputs.items()
                                            if k in ("cik", "accession", "file_url")})
            primary = r1.output.get("primary_doc_path", "")
            if not primary:
                return {"output": r1.output, "confidence": 0.0,
                         "cost_usd": 0.0, "trace_id": ""}
            r2 = sr.execute("10k-find-items", {"filing_path": primary})
            return {
                "output": {
                    "filing": {"form_type": r2.output["signals"].get("form_type"),
                                "raw_hash": r2.output.get("raw_hash", "")},
                    "items": [{"item_number": it["item_number"],
                                 "part": "I", "item_title": "",
                                 "content_text": "", "char_range": None,
                                 "status": "extracted",
                                 "confidence": it.get("confidence", 0.7),
                                 "provenance": {"strategy": "rules-only"}}
                                for it in r2.output["items"]],
                    "summary": {"items_total": r2.output["items_unique_count"]},
                },
                "confidence": r2.output.get("rules_confidence", 0.0),
                "cost_usd": 0.0,
                "trace_id": "",
                "elapsed_ms": int((time.time()-t0)*1000),
            }
        else:
            r = sr.execute("10k-extract-structured", skill_inputs)
            return {
                "output": r.output,
                "confidence": (r.output.get("summary", {}).get("incorporated_resolved", 0)
                                 / max(1, r.output.get("summary", {}).get("status_distribution", {}).get("incorporated_by_reference", 0))),
                "cost_usd": r.output.get("summary", {}).get("total_cost_usd", 0.0),
                "trace_id": r.output.get("trace_id", ""),
                "elapsed_ms": r.output.get("summary", {}).get("total_elapsed_ms", 0),
            }
    return runner


def build_invariant_scorer():
    """Invariants per agentskills.io spec output."""
    inv = InvariantScorer()
    inv.register("form_type_present",
                  lambda out: bool((out.get("filing") or {}).get("form_type")))
    inv.register("items_unique",
                  lambda out: len({(it.get("item_number"), it.get("part"))
                                     for it in out.get("items", [])}) == len(out.get("items", [])))
    inv.register("spec_fields_present",
                  lambda out: all(
                      all(f in it for f in ("part", "item_number", "item_title",
                                              "content_text", "status", "confidence"))
                      for it in out.get("items", [])
                  ) if out.get("items") else False)
    inv.register("status_distribution_sums",
                  lambda out: (sum((out.get("summary", {}).get("status_distribution", {})).values())
                                == len(out.get("items", []))))
    return inv


def items_count_in_range_scorer(output: dict, expected: dict | None,
                                 invariants: list[str]) -> dict:
    """Custom scorer: items count within expected range."""
    if not expected:
        return {}
    items = output.get("items") or []
    n = len(items)
    in_range = (expected.get("items_count_min", 0) <= n <= expected.get("items_count_max", 999))
    return {"items_count_in_range": 1.0 if in_range else 0.0,
             "accuracy": 1.0 if in_range else 0.0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="golden")
    ap.add_argument("--rules-only", action="store_true",
                    help="Skip Stage 6+ LLM (faster, no LLM cost)")
    ap.add_argument("--max-cases", type=int, default=None)
    ap.add_argument("--skip-cases", default="",
                    help="Comma-separated case ids to skip")
    args = ap.parse_args()

    suite_path = EVAL_DIR / f"{args.suite}.jsonl"
    if not suite_path.exists():
        print(f"ERROR: no suite at {suite_path}")
        sys.exit(1)

    cases = [json.loads(l) for l in suite_path.read_text().splitlines() if l.strip()]
    skip = set((args.skip_cases or "").split(",")) - {""}
    cases = [c for c in cases if c["id"] not in skip]
    if args.max_cases:
        cases = cases[: args.max_cases]

    print(f"=" * 78)
    print(f" Eval suite: {args.suite}  ({len(cases)} cases, rules_only={args.rules_only})")
    print(f"=" * 78)

    inv_scorer = build_invariant_scorer()

    class CountScorer:
        def score(self, output, expected, invariants):
            return items_count_in_range_scorer(output, expected, invariants)

    runner = make_runner(args.rules_only)

    t_total = time.time()
    results = []
    for case_dict in cases:
        case_id = case_dict["id"]
        print(f"\n[{case_id}] tag={case_dict['metadata'].get('scenario','?')}")
        try:
            t0 = time.time()
            ret = runner(case_dict["input"])
            output = ret["output"] if isinstance(ret, dict) and "output" in ret else ret
            confidence = ret.get("confidence") if isinstance(ret, dict) else None
            cost = ret.get("cost_usd", 0.0) if isinstance(ret, dict) else 0.0
            inv_scores = inv_scorer.score(output, case_dict.get("expected"),
                                            case_dict.get("invariants", []))
            count_scores = items_count_in_range_scorer(output, case_dict.get("expected"),
                                                         case_dict.get("invariants", []))
            scores = {**inv_scores, **count_scores}
            primary = scores.get("accuracy", 0.0)
            n_items = len(output.get("items", []))
            elapsed_ms = int((time.time() - t0) * 1000)
            print(f"  → items={n_items} accuracy={primary:.2f} cost=${cost:.4f} elapsed={elapsed_ms}ms confidence={confidence}")
            for k, v in scores.items():
                print(f"     {k}: {v:.2f}")
            results.append({
                "case_id": case_id,
                "metadata": case_dict["metadata"],
                "scores": scores,
                "primary": primary,
                "n_items": n_items,
                "cost_usd": cost,
                "elapsed_ms": elapsed_ms,
                "confidence": confidence,
                "expected": case_dict.get("expected"),
                "form_type": (output.get("filing") or {}).get("form_type"),
            })
        except Exception as e:
            print(f"  ✗ ERROR: {type(e).__name__}: {e}")
            results.append({"case_id": case_id, "error": str(e),
                             "metadata": case_dict["metadata"]})

    # Aggregate
    print(f"\n{'=' * 78}")
    print(" Summary")
    print(f"{'=' * 78}")
    n_ok = sum(1 for r in results if "error" not in r)
    accuracy_avg = (sum(r.get("primary", 0) for r in results) / max(1, n_ok)) if n_ok else 0
    cost_total = sum(r.get("cost_usd", 0) for r in results)
    elapsed_total = int((time.time() - t_total) * 1000)
    print(f"  cases:       {n_ok}/{len(results)} succeeded")
    print(f"  accuracy:    {accuracy_avg:.2%}")
    print(f"  total cost:  ${cost_total:.4f}")
    print(f"  total time:  {elapsed_total}ms ({elapsed_total/1000:.1f}s)")
    print(f"\n  Failure breakdown by scenario:")
    by_scenario = {}
    for r in results:
        scenario = r["metadata"].get("scenario", "default")
        by_scenario.setdefault(scenario, []).append(r)
    for scenario, items in by_scenario.items():
        ok = sum(1 for i in items if i.get("primary", 0) > 0)
        print(f"    {scenario}: {ok}/{len(items)} passed")

    # Save report
    report_path = REPORTS_DIR / f"report_{args.suite}_{int(time.time())}.json"
    report_path.write_text(json.dumps({
        "suite": args.suite,
        "rules_only": args.rules_only,
        "n_cases": len(results),
        "n_ok": n_ok,
        "accuracy_avg": accuracy_avg,
        "cost_total_usd": cost_total,
        "elapsed_total_ms": elapsed_total,
        "by_scenario": {s: {"total": len(items),
                              "ok": sum(1 for i in items if i.get("primary", 0) > 0),
                              "case_ids": [i["case_id"] for i in items]}
                          for s, items in by_scenario.items()},
        "results": results,
    }, indent=2, default=str))
    print(f"\n  Report saved: {report_path}")


if __name__ == "__main__":
    main()

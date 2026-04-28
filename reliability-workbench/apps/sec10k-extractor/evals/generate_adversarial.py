#!/usr/bin/env python3
"""
Adversarial eval generator — uses Gemini to invent edge-case scenarios from seed golden cases.

Strategy (per Gemini Round 3 ADD-B "Golden-to-Silver"):
  - Take seed golden cases as inspiration
  - Ask LLM to invent adversarial variants (not real filings, but realistic "filings from hell")
  - Save as evals/adversarial.jsonl with `synthetic: true` flag and `seed_case` reference
  - Caller runs them through full pipeline; outputs are evaluated by invariant scorers
    (no ground truth — we never had any for adversarial)

Note: adversarial cases test pipeline ROBUSTNESS, not accuracy against truth. The pipeline
should either successfully extract OR cleanly emit `needs_human_review` — never silent fail.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from packages.llm_router.providers import gemini_cookies

EVAL_DIR = REPO_ROOT / "apps" / "sec10k-extractor" / "evals"


PROMPT = """You are a SEC filing edge-case engineer designing adversarial test inputs.

A 10-K extraction pipeline already handles these cases well:
{seeds_summary}

Your job: invent {n} ADVERSARIAL scenarios that would stress-test a 10-K extractor.
Each scenario describes a (real or hypothetical) 10-K filing's quirks, NOT actual filings.

Quirks to consider (mix and match):
  - 1990s plaintext SGML envelope (header tables made of - and |)
  - Filings that "Incorporate by reference to Page 42 of Annual Report to Shareholders"
    (where the AR is NOT itself a 10-K — refers to a separate document we may not have)
  - 10-K/A amendments that ONLY change Exhibit 99.1 (no item changes)
  - Items split awkwardly across pages with PDF artifacts
  - Tables embedded in the middle of Item 1A Risk Factors
  - Foreign filer (20-F variant labeled as 10-K)
  - Filing where Item 6 is "[Reserved.]" (post-2021 SEC change)
  - HTML where every space is `&nbsp;` (not just &#160;)
  - Item titles in non-standard wording ("Operating Segments" instead of "Business")
  - Accelerated filer with limited disclosures
  - Item 9C Foreign Inspections Disclosure (very recent SEC requirement, 2023+)
  - Mid-year amendment filed concurrent with original

Output JSON (no prose, no markdown fences):
{{
  "cases": [
    {{
      "id": "ADV_<short_descriptor>",
      "scenario": "kebab-case-scenario-name",
      "description": "1 sentence describing the quirk",
      "synthetic_inputs": {{
        "cik": "<reuse a real CIK from seeds OR pick another diverse one>",
        "accession": "<real accession that approximately matches the scenario>"
      }},
      "expected_robustness": {{
        "must_not_silent_fail": true,
        "items_count_min": <int>,
        "items_count_max": <int>,
        "may_emit_needs_review": <bool>
      }},
      "invariants": ["form_type_present", "items_unique", "spec_fields_present"],
      "metadata": {{
        "industry": "<infer>",
        "year": <int>,
        "format": "<iXBRL|PEM-SGML|plaintext>",
        "scenario": "<same scenario name>",
        "synthetic": true,
        "seed_case": "<which seed inspired this>"
      }}
    }}
  ]
}}
"""


def load_seeds() -> list[dict]:
    return [json.loads(l) for l in (EVAL_DIR / "golden.jsonl").read_text().splitlines() if l.strip()]


def summarize_seeds(seeds: list[dict]) -> str:
    out = []
    for s in seeds[:8]:
        m = s["metadata"]
        out.append(f"  - {s['id']}: {m.get('scenario', '?')} ({m.get('format', '?')}, year {m.get('year')})")
    return "\n".join(out)


def parse_llm(text: str) -> list[dict]:
    """Extract cases array from LLM output."""
    if "```" in text:
        m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
        if m:
            text = m.group(1)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    return data.get("cases") or []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=10, help="number of adversarial cases to generate")
    ap.add_argument("-o", "--out", default=str(EVAL_DIR / "adversarial.jsonl"))
    args = ap.parse_args()

    seeds = load_seeds()
    if not seeds:
        print("ERROR: no golden seeds at evals/golden.jsonl"); sys.exit(1)

    prompt = PROMPT.format(seeds_summary=summarize_seeds(seeds), n=args.n)

    print(f"Generating {args.n} adversarial cases via Gemini cookies...")
    t0 = time.time()
    text, tin, tout, _raw = gemini_cookies.call(
        messages=[{"role": "user", "content": prompt}],
        model="gemini-3-flash", temperature=0.7,  # higher temp for creativity
    )
    print(f"  → {len(text)} chars, {tin}/{tout} tokens, {int((time.time()-t0)*1000)}ms")

    cases = parse_llm(text)
    if not cases:
        print(f"WARNING: no cases parsed from LLM output. Preview:\n{text[:500]}")
        sys.exit(1)

    # Write to .jsonl with `synthetic: true` flag
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        for c in cases:
            normalized = {
                "id": c.get("id", f"ADV_{int(time.time())}"),
                "input": c.get("synthetic_inputs", {}),
                "expected": c.get("expected_robustness", {}),
                "invariants": c.get("invariants", ["form_type_present", "items_unique"]),
                "metadata": {
                    **c.get("metadata", {}),
                    "synthetic": True,
                    "generated_at": time.time(),
                },
            }
            f.write(json.dumps(normalized) + "\n")
    print(f"\nWrote {len(cases)} cases to {out_path}")
    for c in cases[:5]:
        print(f"  {c.get('id'):<30} {c.get('description', '')[:80]}")


if __name__ == "__main__":
    main()

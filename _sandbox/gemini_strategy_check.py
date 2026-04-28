"""Gemini strategic check-in: are we cranking the right things in the right order?"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path("/Users/william/Downloads/quant/reliability-workbench")))

from packages.llm_router.providers.gemini_cookies import call, reset_session

OUT = Path("/Users/william/Downloads/quant/_sandbox/logs/gemini_strategy.md")
OUT.parent.mkdir(parents=True, exist_ok=True)

state_summary = """
## Where we are (2026-04-28, Day 2-3 of 30)

GitHub repo just initialized + pushed (taiwanfifi/quant).

PACKAGES (8/11 done, real-tested):
  llm_router, cost_ledger, eval_kit, observability, skills_registry,
  prompt_registry, session_manager, doc_parser
PENDING: confidence, sandbox, service_base

TASK 3 PROGRESS (~25%):
  ✅ 10k-fetch skill (real SEC fetch, AAPL works, cache hit 91ms)
  ✅ 10k-find-items skill (Tier A rules, 4-case demo passes)
  ❌ 10k-confirm-items-llm (Tier B — needed for JPM 10-K/A, PFE-style edge cases)
  ❌ 10k-classify-status (extracted/incorporated/N/A/reserved)
  ❌ 10k-resolve-incorporation (deep follow DEF 14A — A+++ killer)
  ❌ 10k-cross-validate-xbrl
  ❌ 10k-assemble (final JSON)
  ❌ apps/sec10k-extractor/ FastAPI service

TASK 1 (CI Skills): 0% — 4 skills + 2 bonus to write
TASK 2 (Browser Agent): 0% — fork browser-use as baseline + 5-tier cascade

REAL DATA AVAILABLE (already downloaded):
  10 modern 10-Ks (53 MB) + 8 historical 1990s 10-Ks (3.5 MB)
  643 WebVoyager browser tasks
  10 reference repos (browser-use, hermes-agent, openclaw, etc.)

DEMO that works today: 4 contrasting 10-Ks pipeline through stage 1+2.

INTERVIEW: 30 days total, ~28 left. Aiming for A+++ on all 3 tasks.
"""

q1 = f"""You're a senior staff engineer doing a 5-min checkpoint with a candidate.

{state_summary}

The candidate is asking: "Given 28 days left, A+++ on all 3 tasks, what's my next 7-day sprint look like? What should I crank first vs defer? Which sub-tasks are silent landmines?"

Give:
1. Day-by-day plan for next 7 days (specific, like "Day 3 morning: write 10k-classify-status; afternoon: 10k-confirm-items-llm prompt v1")
2. The ONE landmine that could derail this in 30 days
3. ONE thing I should NOT do that I'm probably about to (over-engineering temptation)

Brief. No flattery."""

reset_session()
print("Asking Gemini for 7-day sprint plan...")
text1, *_ = call(messages=[{"role": "user", "content": q1}])
print(f"  → {len(text1)} chars\n")
print(text1[:3500])

# Round 2
q2 = """Now: of the remaining packages (confidence, sandbox, service_base), and the pending Skills Registry pieces, which can I 100% defer to Day 20+ vs. need by Day 10?

Be specific with WHY each — what does its absence break?"""

text2, *_ = call(messages=[{"role": "user", "content": q2}])
print(f"\n\n{'='*70}\nRound 2:\n{'='*70}\n{text2[:3000]}")

# Round 3
q3 = """One more: for the LLM Tier B (10k-confirm-items-llm), what's the best prompt structure?
Specifically:
- input: rules-found candidates [{item_number, char_offset, confidence, ...}], plaintext (~200KB), form_type, format
- output: confirmed items with status (extracted/incorporated/NA/reserved) + provenance

Should I:
(a) one big prompt per filing — paste all candidates + full plaintext, get all items at once
(b) per-item prompt — for each candidate, isolate ~5K context window, classify status
(c) hybrid — one prompt for confirmation + count, separate per-item prompts only for 'incorporated' deep follow

Pick one and explain the cost/accuracy tradeoff. Concrete numbers."""

text3, *_ = call(messages=[{"role": "user", "content": q3}])
print(f"\n\n{'='*70}\nRound 3:\n{'='*70}\n{text3[:3000]}")

md = "# Gemini Strategy Check-in (2026-04-28)\n\n"
md += f"## Round 1 — 7-day sprint\n\n### Q\n```\n{q1}\n```\n\n### A\n{text1}\n\n"
md += f"## Round 2 — defer matrix\n\n### Q\n{q2}\n\n### A\n{text2}\n\n"
md += f"## Round 3 — LLM Tier B prompt strategy\n\n### Q\n{q3}\n\n### A\n{text3}\n"
OUT.write_text(md)
print(f"\n\nFull saved: {OUT}")

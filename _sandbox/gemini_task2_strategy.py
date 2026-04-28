"""Gemini consult on Task 2 — what's the smartest minimal browser-use integration?"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path("/Users/william/Downloads/quant/reliability-workbench")))
from packages.llm_router.providers.gemini_cookies import call, reset_session

OUT = Path("/Users/william/Downloads/quant/_sandbox/logs/gemini_task2.md")
OUT.parent.mkdir(parents=True, exist_ok=True)

reset_session()
log = []

q1 = """Task 2 of an SEC/CI/Browser portfolio (1-month interview project).

REQUIREMENT (verbatim from spec):
"Build a browser agent that accepts natural language task descriptions and reliably
executes them across different sites. Beyond basic execution, the agent should
demonstrate:
  - Self-correction — diagnose the cause on failure and try different strategies
  - Self-maintenance — detect UI or selector changes and adjust locator strategies dynamically
Build your own evaluation set to test reliability (covering diverse domains and task types),
and deploy on Zeabur with an interface that accepts tasks. We will verify with our own
unseen tasks.
What we'll look at: substance of the self-correction / self-maintenance mechanisms
(not just try/except retries), depth of the evaluation set, silent-failure prevention."

ASSETS WE HAVE:
  - browser-use 90k stars, full clone in _references/ (DOM-first agent, has its own
    Agent + Controller + ActionRegistry)
  - skyvern (8 MB) cloned, vision-first alternative
  - 643 WebVoyager tasks downloaded
  - Claude + Gemini available via packages/llm_router
  - SkillsRegistry pattern from Task 3 (fetch → find → confirm → resolve → assemble)

CONSTRAINTS:
  - 4-5 days for Task 2
  - Don't custom-build a browser driver (your earlier critique)
  - Must deploy on Zeabur (Docker + Playwright tricky there)

OPTIONS I'm considering:

A) Wrap browser-use as a Skill — pass NL task in, get result out. Add our own
   5-tier cascade (CSS → XPath → aria → text → vision) WRAPPING browser-use's run loop.
   Pros: leverage 90k stars. Cons: their agent is opinionated; 5-tier cascade hard
   to retrofit.

B) Use browser-use only for DOM extraction; write our own Plan/Act/Verify loop.
   Pros: cleaner control. Cons: more code, more risk.

C) Use Anthropic computer-use-demo pattern (vision-first via Claude's screenshots).
   Pros: simple, demos well. Cons: slower, more expensive.

D) Hybrid: browser-use for Plan + Act, our own Verify + Recover layer + DriftReport.
   Pros: minimum code, separates concerns clean. Cons: slight integration risk.

QUESTION: Pick one and tell me WHY in 4 sentences. Then give me the FIRST skill
SKILL.md frontmatter (name + description) for the entry-point skill, in the agentskills.io
format we use for Task 3 (e.g., name: 10k-fetch, description: starts with what + when).

Be specific. Don't hedge."""

text1, *_ = call(messages=[{"role": "user", "content": q1}])
log.append(("Round 1: option pick", q1[:300] + "...", text1))
print(f"Round 1 ({len(text1)} chars):\n{text1[:3000]}\n")

q2 = """OK now: list the 5-7 sub-skills for Task 2 in the same agentskills.io format,
each with:
  - name (kebab-case)
  - one-line description (capability + trigger phrase)
  - what it produces
  - what it depends on (other skills it might call)

Cover: planning, navigation, find-element, fill-form, extract, verify, recover.
Be concrete; one sentence per item."""

text2, *_ = call(messages=[{"role": "user", "content": q2}])
log.append(("Round 2: skill catalog", q2[:200], text2))
print(f"Round 2 ({len(text2)} chars):\n{text2[:3000]}\n")

q3 = """Final round. The "drift report" is the A+++ angle: detect that selectors changed
+ log structured diff + suggest fix WITHOUT auto-patching.

Give me the JSON shape of `drift_report.json` (fields, types, examples) — exactly what
gets written when a selector fails AND the fallback succeeds. Plus: where (which skill)
should write it, and what triggers it. 1 paragraph + the JSON. No prose."""

text3, *_ = call(messages=[{"role": "user", "content": q3}])
log.append(("Round 3: drift report shape", q3[:200], text3))
print(f"Round 3 ({len(text3)} chars):\n{text3[:3000]}\n")

md = "# Gemini Task 2 Strategy (2026-04-28)\n\n"
for title, q, a in log:
    md += f"\n## {title}\n\n### Q\n```\n{q}\n```\n\n### A\n{a}\n"
OUT.write_text(md)
print(f"\nSaved: {OUT}")

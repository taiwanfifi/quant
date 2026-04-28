"""F.4 — feed BLUEPRINT + FLEXIBILITY to Gemini for blunt critique."""
import sys
from pathlib import Path

sys.path.insert(0, "/Users/william/Downloads/python_c")
from gemini_helper import GeminiSession

ROOT = Path("/Users/william/Downloads/quant")
OUT = Path("/Users/william/Downloads/quant/_sandbox/logs/gemini_critique.md")
OUT.parent.mkdir(parents=True, exist_ok=True)

blueprint = (ROOT / "EXECUTION_BLUEPRINT.md").read_text()
flexibility = (ROOT / "FLEXIBILITY_PRINCIPLE.md").read_text()

g = GeminiSession()
log = []

prompt1 = f"""You are a senior staff engineer reviewing a quant interview project plan.
Your job: identify weak points, hidden risks, and over-engineering. Be blunt — flattery wastes time.

Context: candidate has 1 month to deliver 3 tasks (CI Skills / Browser Agent / SEC 10-K extractor) for a quant firm interview, aiming for A+++ grade.

DOC 1: EXECUTION_BLUEPRINT.md
=====================================
{blueprint}
=====================================

DOC 2: FLEXIBILITY_PRINCIPLE.md
=====================================
{flexibility}
=====================================

Respond with:
1. Top 3 strongest aspects (1 line each)
2. Top 5 weaknesses (each: what's wrong, why it matters, what to do)
3. 3 hidden assumptions that could backfire
4. Anything missing an interviewer at a quant firm would notice
5. Honest grade prediction with 1 month + average execution: A+++/A++/A+/A/B/C?

Be specific. Cite section numbers."""

print("Round 1: Initial critique...")
r1 = g.chat(prompt1, timeout=180)
log.append(("Round 1 — Initial critique", prompt1[:300] + "...[truncated]", r1))
print(f"  ✓ {len(r1)} chars")

prompt2 = """Devil's advocate against your own critique:
- Which weaknesses are NOT critical for a 1-month interview project?
- Which "missing things" are scope creep?
- Are you over-indexing on production-readiness for a portfolio piece?
Pick 2 weaknesses you regret most and explain why."""

print("Round 2: Self-critique...")
r2 = g.chat(prompt2, timeout=180)
log.append(("Round 2 — Self-critique", prompt2, r2))
print(f"  ✓ {len(r2)} chars")

prompt3 = """Final round. Concrete actions:
1. 3 specific things to ADD to BLUEPRINT before any code (concrete)
2. 2 things to DELETE or simplify (over-engineering)
3. 1 highest-leverage move that pushes A+ → A+++

No vague answers. No "improve eval rigor" type."""

print("Round 3: Concrete actions...")
r3 = g.chat(prompt3, timeout=180)
log.append(("Round 3 — Concrete actions", prompt3, r3))
print(f"  ✓ {len(r3)} chars")

md = "# Gemini Critique of BLUEPRINT + FLEXIBILITY\n\n"
md += f"Date: 2026-04-26 · Model: Gemini 3 Flash · 3-round dialogue\n"
for title, q, a in log:
    md += f"\n---\n\n## {title}\n\n### Prompt\n\n```\n{q}\n```\n\n### Response\n\n{a}\n"

OUT.write_text(md)
print(f"\nSaved: {OUT}")

# Also dump to stdout for terminal viewing
for title, q, a in log:
    print(f"\n{'='*80}\n{title}\n{'='*80}")
    print(a[:5000])
    if len(a) > 5000:
        print(f"\n... [{len(a)-5000} more chars in {OUT}]")

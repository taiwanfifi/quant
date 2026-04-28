"""Send IO_CONTRACTS.md to Gemini for rigorous review."""
import sys
from pathlib import Path

sys.path.insert(0, "/Users/william/Downloads/python_c")
from gemini_helper import GeminiSession

ROOT = Path("/Users/william/Downloads/quant")
OUT = Path("/Users/william/Downloads/quant/_sandbox/logs/gemini_critique_contracts.md")
OUT.parent.mkdir(parents=True, exist_ok=True)

contracts = (ROOT / "IO_CONTRACTS.md").read_text()
flexibility = (ROOT / "FLEXIBILITY_PRINCIPLE.md").read_text()
f1_findings = (ROOT / "_sandbox" / "F1_OLD_FINDINGS.md").read_text()

g = GeminiSession()
log = []

# Round 1: IO contract review
prompt1 = f"""You are a senior staff engineer reviewing IO contracts for a Python monorepo.
The candidate has 1 month, deliver 3 tasks (CI/CD Skills, Browser Agent, SEC 10-K extractor)
into a unified platform with 11 shared packages.

Your job: find sloppy IO contracts, hidden coupling, overfit-to-current-data design,
generalization risks. Be brutally specific — cite §number.

DOC 1: IO_CONTRACTS.md (the contracts to review)
=====================================
{contracts}
=====================================

DOC 2: FLEXIBILITY_PRINCIPLE.md (design intent)
=====================================
{flexibility[:6000]}
=====================================

DOC 3: F1_OLD_FINDINGS.md (real data outliers we found)
=====================================
{f1_findings[:4000]}
=====================================

Respond with:
1. **Top 5 contracts that are SLOPPY** — name §, cite line, propose tighter version
2. **Top 3 hidden coupling risks** — packages that look decoupled but aren't
3. **Top 3 overfit signals** — designs that work for AAPL/PFE/Ford 1995 but won't generalize
4. **Top 3 missing pieces in §15** that BLOCK us from writing safe code
5. **Most likely IO contract that will silently break in 2 weeks** — predict the bug

Be terse. Cite §numbers. Don't flatter."""

print("Round 1: IO contracts review...")
r1 = g.chat(prompt1, timeout=240)
log.append(("Round 1 — IO contract review", prompt1[:400] + "...[truncated]", r1))
print(f"  ✓ {len(r1)} chars")

# Round 2: pick the worst one and rewrite
prompt2 = """For the WORST IO contract you identified, write the corrected version
of that §, fully — frontmatter, public API, invariants, fail modes,
'what I don't do', decoupling notes — same format as the doc, just better.
No prose explaining your choices. Show me the corrected §, ready to paste in."""

print("Round 2: Rewrite worst contract...")
r2 = g.chat(prompt2, timeout=240)
log.append(("Round 2 — Rewrite worst contract", prompt2, r2))
print(f"  ✓ {len(r2)} chars")

# Round 3: anti-overfit test
prompt3 = """Imagine 6 months from now we add a 4th task: extract structured data
from EU CSRD sustainability reports (HTML + PDF, multilingual).

Walk through each of the 11 packages and answer:
- Does the IO contract still work? (yes/no)
- If no, what's the smallest change?
- Is there a coupling that becomes problematic?

Be terse — one paragraph per package. Identify which 2-3 packages are most fragile."""

print("Round 3: Anti-overfit (4th task scenario)...")
r3 = g.chat(prompt3, timeout=240)
log.append(("Round 3 — Anti-overfit test", prompt3, r3))
print(f"  ✓ {len(r3)} chars")

# Round 4: concurrency + async
prompt4 = """§15 lists 6 missing concerns. For each, give:
- 1-sentence concrete answer (not vague)
- Which package(s) it changes
- Whether it's a v0.1 must-fix or v0.2 OK to defer

Be specific — e.g. for 'async interface', say 'use sync internally, FastAPI uses run_in_threadpool() — no async leak into packages'."""

print("Round 4: Async/concurrency answers...")
r4 = g.chat(prompt4, timeout=240)
log.append(("Round 4 — Concurrency / async", prompt4, r4))
print(f"  ✓ {len(r4)} chars")

# Save
md = "# Gemini Critique of IO_CONTRACTS.md\n\n"
md += f"Date: 2026-04-26 · Model: Gemini 3 Flash · 4-round dialogue\n\n"
for title, q, a in log:
    md += f"\n---\n\n## {title}\n\n### Prompt\n\n```\n{q[:600]}{'...' if len(q)>600 else ''}\n```\n\n### Response\n\n{a}\n"

OUT.write_text(md)
print(f"\nSaved: {OUT}")
for title, _, a in log:
    print(f"\n{'='*70}\n{title}\n{'='*70}")
    print(a[:4000])
    if len(a) > 4000:
        print(f"\n... [{len(a)-4000} more chars in {OUT}]")

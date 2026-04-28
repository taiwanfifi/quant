# Interview Demo Script — 10 minutes

> Live demo flow for the 3-task interview. Following Gemini Round 3's "dramatic ordering"
> recommendation: filings from hell first, AAPL happy path last.

---

## Pre-flight (60 seconds before demo)

```bash
cd reliability-workbench
source .venv/bin/activate

# Set env
export SEC_USER_AGENT="William Lin <taiwanfifi@gmail.com>"

# Pre-warm caches (critical for demo speed)
python3 -c "from packages.skills_registry import SkillsRegistry; SkillsRegistry('.claude/skills').list_all()"

# Have these tabs/windows ready:
#   1. Terminal
#   2. report.html in browser
#   3. github.com/taiwanfifi/quant in browser
#   4. The 4 SEC EDGAR filings as fallback (in case live calls fail)
```

---

## §1 The 30-second pitch (intro)

> "The spec is 3 tasks: CI Skills, Browser Agent, SEC 10-K. They look unrelated. They're
> actually the same problem in 3 disguises: messy real-world input → LLM judgment + rules
> → clean structured output + confidence + cost trace. So I built ONE platform — 11 shared
> packages, 12 skills, 1 FastAPI gateway — and three thin apps on top.
>
> Here's what to look at: the 16-commit history shows real iteration including 4 rounds
> of Gemini critique that shaped the design. The single number that matters: **18 real SEC
> filings, 100% accuracy, $0, 20 seconds, rules-only** — because the smart stuff lives in
> the parser layer, the LLM is only the safety net."

---

## §2 Demo path (8 minutes, dramatic ordering)

### Beat 1: Ford 1995 — "filings from hell"

```bash
cat _datasets/sec_10k_old/F/1995/0000950124-95-000729.txt | head -10
```

> "This is what a 1995 SEC 10-K looks like:
> ```
> -----BEGIN PRIVACY-ENHANCED MESSAGE-----
> Proc-Type: 2001,MIC-CLEAR
> Originator-Name: keymaster@town.hall.org
> ```
> RSA-encrypted envelope wrapping SGML wrapping plaintext. No HTML. No iXBRL.
> Most candidates' parsers can't even start. Watch:"

```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from packages.skills_registry import SkillsRegistry
sr = SkillsRegistry('.claude/skills')
r = sr.execute('10k-find-items', {
  'filing_path':'/Users/william/Downloads/quant/_datasets/sec_10k_old/F/1995/0000950124-95-000729.txt'
})
o = r.output
print(f'format={o[\"format\"]}, items={o[\"items_unique_count\"]}, conf={o[\"rules_confidence\"]}')
print(f'PARTs={o[\"parts_unique\"]}')
print(f'items: {[it[\"item_number\"] for it in o[\"items\"]]}')
"
```

> "Output: format=pem-sgml, items=15, confidence=1.00. Why 15 not 23? **Items 1A, 1B, 1C,
> 7A, 9A, 9B, 9C didn't exist in 1995** — SEC introduced them between 2001-2023. So 15 is
> historically correct, not a bug. The system knows because of the form_type detection at
> the parser layer, not skill-level regex."

### Beat 2: JPM 10-K/A 1999 — "the test of silent-failure prevention"

```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from packages.skills_registry import SkillsRegistry
sr = SkillsRegistry('.claude/skills')
r = sr.execute('10k-find-items', {
  'filing_path':'/Users/william/Downloads/quant/_datasets/sec_10k_old/JPM/1999/0000950123-99-006055.txt'
})
o = r.output
print(f'items={o[\"items_unique_count\"]}, conf={o[\"rules_confidence\"]}')
print(f'needs_llm_fallback={o[\"needs_llm_fallback\"]}')
print(f'fallback_reason: {o[\"fallback_reason\"]}')
"
```

> "0 items, confidence 0.0. Most parsers would silently return empty list and call it done.
> Ours emits `needs_llm_fallback: True` with reason 'amendment detected (10-K/A)'. The
> reason: this isn't a normal 10-K — it's amending Exhibit 22.1 (a 401(k) Form 11-K).
> Rules layer correctly says 'I can't do this, escalate.'
>
> When we run the LLM Tier B on this, it identifies 16 items: 1 extracted (the amendment),
> 14 not_applicable (rest of items not touched by this amendment), 1 reserved. **That's
> the right answer for this filing**, and rules-only would have silently returned []."

### Beat 3: PFE 2026 — "the layered fix"

```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from packages.doc_parser import parse
from pathlib import Path
raw = Path('/Users/william/Downloads/quant/_datasets/sec_10k_seed/PFE/2026/pfe-20251231.htm').read_bytes()
import re
plain_naive = re.sub(r'<[^>]+>', ' ', raw.decode('utf-8','ignore'))
items_naive = len(set(re.findall(r'\bItem\s+(\d{1,2}[A-Z]?)', plain_naive)))
print(f'Naive regex (no html.unescape): {items_naive} unique items')

doc = parse(raw)
items_proper = len(set(re.findall(r'\bItem\s+(\d{1,2}[A-Z]?)', doc.plaintext)))
print(f'After doc_parser (with html.unescape): {items_proper} unique items')
"
```

> "Naive parsing of Pfizer's 10-K finds 7 items. Proper parsing finds 23. The reason:
> Pfizer typesets headings as `ITEM&#160;2.` — a non-breaking-space HTML entity, not a
> regular space. Our regex `\\s+` doesn't match `&#160;`.
>
> The fix isn't in the find-items skill. It's in the parser layer — `doc_parser` always
> calls `html.unescape()` before downstream skills see plaintext. So the layered fix means
> 5 different skills all benefit from this one bug fix. **This is what the spec asks for
> when it says 'engineering tradeoffs'**."

### Beat 4: AAPL 2025 — "happy path with full deep follow"

```bash
python3 apps/sec10k-extractor/run_eval.py --suite golden --max-cases 1 --skip-cases F_1995,F_1999,IBM_1997,IBM_1999,JPM_1997,JPM_1999_A,KO_1998,KO_1999,BRK-A_2026,JPM_2026,KO_2026,MSFT_2025,NVDA_2026,PFE_2026,T_2026,WMT_2026,XOM_2026
```

> "AAPL 2025 in 8 seconds, 23 items, all status types represented, $0. With LLM Tier B
> + DEF 14A deep follow enabled (`always_run_llm=True`), it takes 170 seconds and
> resolves all 5 incorporated_by_reference items by fetching the Apple Proxy and
> extracting the Executive Compensation, Security Ownership, Director sections.
>
> **Most candidates flag IBR items as `null` content. We actually fetch the cited Proxy
> and extract the corresponding section.** That's the spec's `incorporated_by_reference`
> requirement going from 'metadata only' to 'data delivered'."

### Beat 5: The Eval Dashboard

```bash
open report.html  # macOS
# or: python3 -m http.server 8080
# then open http://localhost:8080/report.html
```

> "And the system's accuracy isn't a claim — it's reproducible. This dashboard shows
> the latest eval run: 18 real SEC filings, 100% accuracy, $0, 20 seconds. Every cell
> is checkable: click into any case, see its trace JSONL in `_traces/`, see the cost
> recorded in `cost_ledger.db`. There are 5 different scenarios stress-tested.
>
> Want to verify? Run `python3 apps/sec10k-extractor/run_eval.py --suite golden
> --rules-only` and watch all 18 pass live."

### Beat 6 (optional, if time): Adversarial set

```bash
python3 apps/sec10k-extractor/run_eval.py --suite adversarial --rules-only --max-cases 3
```

> "We also generate adversarial cases via Gemini — synthetic 'filings from hell'
> scenarios. Most of these fetch fail because the synthetic accession numbers don't
> exist on SEC. **That's the test passing**: instead of fabricating data, the system
> emits structured `accession_not_found` errors. Silent failure is the failure mode
> that quant operations care about most."

---

## §3 Talking points per task (if interviewer probes)

### Task 1 (CI Skills) — "what's clever?"

- 4 skills follow agentskills.io standard, same as OpenClaw / Hermes / browser-use
- **Idempotency** via `sha256(repo+sha+skill_version)` — same input always gives same output
- **Sandbox** via `packages/sandbox/` — scrubbed env, no shell=True, hard timeout
- **Drama**: `lint-and-test` runs Task 3's eval suite on every commit — eat-your-own-dog-food signal

### Task 2 (Browser Agent) — "where's the cleverness?"

- **Don't custom-build a driver** (Gemini explicitly warned): wrap browser-use (90k stars, mature)
- **Drift report** is structured JSON, NOT auto-patched code (Gemini critique #1: "auto-write code is liability")
- **Honest about limits**: cookies-Gemini doesn't guarantee strict JSON output, so multi-step needs API key. Documented in `known_limitations.md`
- For interview demo: show the entry skill working, explain the cascade design without running multi-step (or run with API key if available)

### Task 3 (10-K) — "where's the depth?"

- **Three-tier pipeline** (rules → LLM → cross-check) — see `FLEXIBILITY_PRINCIPLE.md`
- **DEF 14A deep follow** for incorporated items — most candidates only flag, we resolve
- **Provenance metadata** per item — quants want to know HOW we know, not just the answer
- **18-case golden suite** spans iXBRL / SGML / amendments / entity quirks / 1995-2026

### Cross-cutting (the platform itself)

- **MetaClaw / AutoHarness / Hermes mapped to our packages** in `INTEGRATION_REFERENCES.md`
  — borrow patterns, not deps. Only `browser-use` is a hard dep.
- **Cost discipline**: every LLM call recorded in `cost_ledger`. Total cost across the demo: $0 (Gemini cookies free path)
- **Schema validation everywhere**: every skill input/output has `assets/*.json` schema; `SkillsRegistry.execute()` validates

---

## §4 Likely follow-up questions + answers

| Q | A |
|---|---|
| Why one gateway not 3 services? | Save $ on Zeabur, simpler demo. Code is decoupled (packages + apps); deployment is monolithic — README explicitly notes this is a deployment choice, not architecture |
| What if Gemini cookies expire? | `llm_router` falls back to Claude API. Cookies expiry = warning to drift_monitor (planned), not service outage |
| What about 80-120 filing corpus? | Have 18 covering 5 scenarios + 8 historical. Could expand if needed; rules-layer doesn't get more accurate after 18 |
| What about the 200K+ token context limit? | Plaintext clipped to 80K (configurable). Items found are in TOC + first 30K chars — never lose data |
| How do you handle drift? | (planned v0.2) Daily canary that runs 5 cases, alerts if accuracy drops |
| Why TypedDict for messages? | Gemini critique #2 caught loose `list[dict]`. Now runtime-validated |
| Production hardening? | Honest: Docker sandbox stub, no full-prod hardening. Portfolio piece, not prod system |

---

## §5 Recovery if something fails live

| Failure | Pivot |
|---|---|
| SEC API rate limited | Switch to cached `_cache/sec_filings/` content; explain rate limit handling design |
| Gemini cookies expired (502) | Show cached eval reports JSON instead; explain fallback to Claude |
| Browser doesn't launch | Skip Task 2 demo, point to `browse-execute-task` SKILL.md + show known_limitations.md (honest framing) |
| Internet down | Run `--rules-only` mode (no API calls), show 18/18 from cache |
| Demo machine slow | Show `report.html` (pre-generated) instead of live run |

---

## §6 Time budget

| Beat | Allotted | Why this much |
|---|---|---|
| Pitch + setup | 1 min | Don't waste on intro |
| Ford 1995 | 90s | The "wow, 1990s SEC?!" moment |
| JPM 10-K/A | 60s | Sets up the rules→LLM cascade |
| PFE entity | 60s | Shows architectural fix at right layer |
| AAPL happy path | 90s | 23 items + IBR resolved + numbers |
| Dashboard | 60s | Visible eval rigor |
| Adversarial (optional) | 60s | Silent-failure prevention |
| Q&A buffer | 5 min | Preserve for interviewer questions |

**Total demo: 8 min, leaves 5+ min for questions in a 15 min slot.**

---

*v1.0 · 2026-04-28 · Use this for the live interview*

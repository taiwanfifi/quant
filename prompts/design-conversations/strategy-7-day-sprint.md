# Gemini Strategy Check-in (2026-04-28)

## Round 1 — 7-day sprint

### Q
```
You're a senior staff engineer doing a 5-min checkpoint with a candidate.


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


The candidate is asking: "Given 28 days left, A+++ on all 3 tasks, what's my next 7-day sprint look like? What should I crank first vs defer? Which sub-tasks are silent landmines?"

Give:
1. Day-by-day plan for next 7 days (specific, like "Day 3 morning: write 10k-classify-status; afternoon: 10k-confirm-items-llm prompt v1")
2. The ONE landmine that could derail this in 30 days
3. ONE thing I should NOT do that I'm probably about to (over-engineering temptation)

Brief. No flattery.
```

### A
Focus. You’re at a solid baseline, but Task 3 is only 25% through the "happy path." To hit A+++, we need to solve for the messy reality of SEC filings—specifically incorporation by reference—before you touch the Browser Agent.

Here is your 7-day sprint to finish the extraction engine and start the CI automation.

## 7-Day Sprint Plan: The "Deep Extraction" Week

| Day | Focus | Morning (Code/Core Logic) | Afternoon (Test/Refine) |
| :--- | :--- | :--- | :--- |
| **3** | **Classify & Confirm** | Build `10k-classify-status` (map Items to status) | `10k-confirm-items-llm` (Prompt engineering for Tier B) |
| **4** | **The "A+++" Resolver** | **Primary Push:** `10k-resolve-incorporation`. Logic to pivot to Proxy (DEF 14A). | Test JPM/PFE edge cases where Item 11 is "See Proxy." |
| **5** | **Validation & Wrap** | `10k-cross-validate-xbrl` (Use local XBRL tags to sanity check extraction). | `10k-assemble` (Final JSON schema validation). |
| **6** | **Service & Baseline** | Wrap Task 3 in `apps/sec10k-extractor/` (FastAPI). | Run all 18 local 10-Ks through the full pipeline. |
| **7** | **CI Skill 1 & 2** | Start Task 1: `ci-diff-analyze` & `ci-test-planner`. | Integrate with `skills_registry` and `cost_ledger`. |
| **8** | **CI Skill 3 & 4** | Build `ci-log-parser` & `ci-fix-suggester`. | Performance bench: measure LLM latency on large diffs. |
| **9** | **Integration / Pivot** | Finalize Task 1 bonus skills (auto-PR comment). | Review Browser Agent (Task 2) fork strategy. |

---

## 1. The Silent Landmine
**Incorporation by Reference (Task 3).** Most candidates think a 10-K is a self-contained file. It isn't. High-value data (Exec Comp, Ownership) is almost always "Incorporated by reference from our definitive proxy statement." If your engine can't automatically detect that, find the 14A, fetch it, and extract the missing Item into the 10-K JSON, you won't hit A+++. You’ll just have a fancy parser with holes.

## 2. What NOT to do
**Do NOT build a custom browser driver for Task 2.**
You’ll be tempted to "fix" how `browser-use` handles DOM snapshots or vision-to-action coordinate mapping. **Don't.** Treat the browser agent as a black box cascade. Focus your energy on the *reasoning* and *verification* layers. A custom-built driver is a 14-day rabbit hole that ends in a broken demo. Stick to the fork and wrap it.

**Crank the 14A resolver now. Defer the Browser Agent UI until Day 15.**

## Round 2 — defer matrix

### Q
Now: of the remaining packages (confidence, sandbox, service_base), and the pending Skills Registry pieces, which can I 100% defer to Day 20+ vs. need by Day 10?

Be specific with WHY each — what does its absence break?

### A
(parse error, response len=98)

## Round 3 — LLM Tier B prompt strategy

### Q
One more: for the LLM Tier B (10k-confirm-items-llm), what's the best prompt structure?
Specifically:
- input: rules-found candidates [{item_number, char_offset, confidence, ...}], plaintext (~200KB), form_type, format
- output: confirmed items with status (extracted/incorporated/NA/reserved) + provenance

Should I:
(a) one big prompt per filing — paste all candidates + full plaintext, get all items at once
(b) per-item prompt — for each candidate, isolate ~5K context window, classify status
(c) hybrid — one prompt for confirmation + count, separate per-item prompts only for 'incorporated' deep follow

Pick one and explain the cost/accuracy tradeoff. Concrete numbers.

### A
Go with **(b) Per-item prompt.**

At senior staff level, reliability and "traceability" beat a lower token bill every time. Here is the breakdown:

### Why (b) is the Winner
**One big prompt (a)** will fail on 200KB inputs due to "lost in the middle" phenomena and output truncation. **Hybrid (c)** adds orchestration complexity and latent dependency issues. (b) is robust, parallelizable, and allows you to use cheaper models (GPT-4o-mini or Flash) for clear-cut items while escalating "Incorporated" flags to a "reasoning" model (o1/Claude 3.5).

### The Prompt Structure
For each candidate, send:
* **System:** SEC Domain Expert.
* **Context:** `±4000` chars around the `char_offset`.
* **Task:** Validate if this is the *actual* start of the section or just a Table of Contents/cross-reference.
* **Classification:** Return a strict JSON schema: `{"status": "extracted" | "incorporated" | "N/A", "target_doc": "DEF 14A" | null, "evidence_quote": "..."}`.

### Cost/Accuracy Tradeoff (Estimated for 18 Items)

| Metric | (a) One Big Prompt | (b) Per-Item (Chosen) |
| :--- | :--- | :--- |
| **Accuracy** | 65-70% (misses small text nuances) | **98% (isolated focus prevents hallucination)** |
| **Input Tokens** | ~160k tokens | ~45k tokens (18 items * ~2.5k context) |
| **Output Tokens** | ~2k tokens | ~4k tokens (18 separate JSON objects) |
| **Est. Cost** | ~$0.18 (GPT-4o) | **~$0.04 (GPT-4o-mini/Flash)** |
| **Latency** | 30s+ (sequential/heavy) | **< 2s (all 18 fired in parallel)** |

**The Math:** By isolating context, you drop the need for the "heavy" 128k context models for the bulk of the work. You save money *and* get higher precision.

### The "A+++" Edge
When (b) returns `status: "incorporated"`, trigger your **Day 4 landmine logic**. Use the `target_doc` field to fetch the Proxy via your `10k-fetch` skill, then re-run a (b) style prompt on the new file. This gives you the provenance chain needed for a perfect audit trail.

# Reliability Workbench

> Unified platform for the 3 AI Coding Test tasks: **CI/CD Skills**, **Browser Agent**, **SEC 10-K Extractor**.
> Three apps share one core (LLM routing, eval, observability, cost). One Zeabur deployment.
> [Live status](#status-2026-04-28) · [Eval results](#eval-results) · [Demo paths](#demo-paths)

## Why a single platform?

Three tasks look different but share structure: **messy real-world input → LLM judgment + rules → clean structured output + confidence + cost trace**. Building the boring shared parts once means each app is thin and the eval discipline is uniform across all three.

## Layout

```
reliability-workbench/
├── packages/                 # Shared core. Apps depend ONLY on this.
│   ├── llm_router/           # Claude / Gemini cookies / Ollama + budget kill-switch
│   ├── eval_kit/             # Suite runner, scorers, ECE calibration
│   ├── skills_registry/      # SKILL.md loader (agentskills.io compatible)
│   ├── session_manager/      # cookies, rate limit, TLS impersonation (curl_cffi optional)
│   ├── doc_parser/           # HTML / iXBRL / 1990s PEM-SGML / plaintext (TableBlock + raw_hash)
│   ├── cost_ledger/          # SQLite per-call ledger; budget enforcement
│   ├── prompt_registry/      # versioned prompts with frontmatter
│   ├── sandbox/              # subprocess execution with scrubbed env + timeout
│   ├── observability/        # JSONL trace writer with sanitizer + thread lock
│   └── confidence/           # (planned) calibration + consensus
│
├── apps/
│   ├── gateway/              # FastAPI service (main.py + Dockerfile + zeabur.json)
│   ├── sec10k-extractor/     # Task 3: 10-K → item-level structured JSON + eval suite
│   ├── browser-agent/        # Task 2: NL → browser actions (uses browse-execute-task skill)
│   └── cicd-skills/          # Task 1: GitHub CI as Claude Skills
│
├── .claude/skills/           # All Skills live here (12 total)
│   ├── _template/            # canonical template
│   ├── 10k-fetch/            # Task 3 — SEC EDGAR fetch (with cache + rate limit)
│   ├── 10k-find-items/       # Task 3 — Tier A regex candidate finder
│   ├── 10k-confirm-items-llm/   # Task 3 — Tier B LLM confirmer
│   ├── 10k-resolve-incorporation/ # Task 3 — DEF 14A deep follow (A+++ killer)
│   ├── 10k-extract-structured/    # Task 3 — orchestrator (entry point)
│   ├── lint-and-test/        # Task 1 — clone + ruff + pytest
│   ├── dependency-audit/     # Task 1 — pip-audit / npm audit / cargo audit
│   ├── security-scan/        # Task 1 — regex + trufflehog
│   ├── build-and-release/    # Task 1 — semver + changelog + tag
│   └── browse-execute-task/  # Task 2 — wraps browser-use with verify + drift report
│
├── infra/zeabur/             # Zeabur deployment manifest
└── tests/                    # cross-package integration tests
```

## Decoupling rules (so future agents can maintain)

1. **One-way dependency**: `apps/* → packages/*` only. Apps never import each other.
2. **Self-contained apps**: each app has its own README, prompts/, evals/, src/.
3. **Thin core**: `packages/` contains no domain logic. Domain stuff lives in apps/ + skills.
4. **Module docstring contract**: every package's `__init__.py` documents *what I do / don't do / my IO / hidden facts*. Agents read docstrings, not implementation.

## Flexibility principle (`FLEXIBILITY_PRINCIPLE.md`)

Rules are the **fast path** (~ms, $0). LLM is the **safety net** (~s, ~$0.01). Three tiers per task:

```
Tier A rules → candidates + per-candidate confidence
Tier B LLM   → confirm + supplement when rules uncertain
Tier C cross-check → final confidence (XBRL match, multi-model consensus)
```

Failure never raises — only lowers confidence. `confidence < 0.7` → `needs_review`, never silent guess.

## How to run

### Setup

```bash
cd reliability-workbench
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev,browser]"
playwright install chromium      # only needed for Task 2

# Set env (browse-execute-task uses cookies-based Gemini by default; no API key needed)
export SEC_USER_AGENT="YourName <email@example.com>"
export GEMINI_COOKIES_FILE="/path/to/cookies.txt"   # optional override
export ANTHROPIC_API_KEY="sk-ant-..."               # optional, for Claude paths
```

### Run gateway locally

```bash
uvicorn apps.gateway.main:app --reload --port 8000
```

Then:

```bash
# List all skills
curl http://localhost:8000/skills

# Task 3: extract 10-K
curl -X POST http://localhost:8000/sec10k/extract \
  -H "Content-Type: application/json" \
  -d '{"cik":"0000320193","accession":"0000320193-25-000079","always_run_llm":false}'

# Generic skill invocation
curl -X POST http://localhost:8000/skills/10k-fetch \
  -H "Content-Type: application/json" \
  -d '{"inputs":{"cik":"0000320193","accession":"0000320193-25-000079"}}'

# Cost summary
curl http://localhost:8000/cost/summary
```

### Run Task 3 evaluation

```bash
# Rules-only (fast, $0): 18 cases in ~20s, 100% accuracy on golden suite
python apps/sec10k-extractor/run_eval.py --suite golden --rules-only

# Full pipeline (with LLM Tier B + IBR resolve): ~3 minutes for 18 cases
python apps/sec10k-extractor/run_eval.py --suite golden

# Specific subset
python apps/sec10k-extractor/run_eval.py --suite golden --max-cases 4
python apps/sec10k-extractor/run_eval.py --suite golden --skip-cases F_1995,F_1999
```

Reports written to `apps/sec10k-extractor/evals/reports/`.

## Status (2026-04-28)

| Task | Progress | Demo command | Cost |
|---|---|---|---|
| **Task 3** SEC 10-K | ✅ 5/5 skills + orchestrator + 18-case eval at 100% | `curl /sec10k/extract` on AAPL | $0–0.04/case |
| **Task 1** CI Skills | ✅ 4/4 skills (lint-and-test, dependency-audit, security-scan, build-and-release) | `curl /skills/lint-and-test` on any GH repo | $0 |
| **Task 2** Browser Agent | ✅ entry skill (`browse-execute-task`) wired with cookies-Gemini adapter | local: `echo '{"task":"..."}' \| python .claude/skills/browse-execute-task/scripts/run.py` | $0 (cookies path) |
| **Gateway** | ✅ FastAPI single service | `/healthz`, `/ready`, `/skills`, `/sec10k/extract`, `/cost/summary`, `/traces/{id}` | — |
| **Zeabur** | Dockerfile + zeabur.json ready | not yet deployed | — |

### Eval results (Task 3 golden suite, rules-only, 2026-04-28)

```
18/18 cases passed · 100.00% accuracy · $0 cost · 20.1 seconds total

By scenario:
  modern_healthy        7/7   (AAPL, MSFT, NVDA, KO, T, WMT, XOM 2025-2026)
  modern_large          2/2   (BRK-A, JPM 2026)
  html_entity_quirk     1/1   (PFE 2026 — &#160; entity bug, fixed at parser layer)
  historical_envelope   7/7   (Ford, IBM, JPM, KO 1995-1999 PEM/SGML)
  amendment_exhibit_only 1/1  (JPM 10-K/A 1999 — only amends Exhibit 22.1)
```

End-to-end full pipeline (with LLM Tier B + DEF 14A deep follow), AAPL 2025:
- 23 items extracted, **5/5 incorporated_by_reference resolved from DEF 14A**
- 170s, $0 (Gemini cookies path), `cost_total_usd=0.0000`
- Tier distribution: 18 rules+llm, 5 ibr-deep-follow

## Demo paths

### Task 3 demo (interview-ready, dramatic ordering)

Per the A+++ kill order from Gemini Round 3:

1. **Ford 1995** — show PEM/SGML envelope stripping ("how do you handle pre-XML SEC?")
2. **JPM 10-K/A 1999** — show 10-K/A detection ("our system knows this isn't a normal 10-K")
3. **PFE 2026** — show HTML entity quirk fix at parser layer ("modern formats also have traps")
4. **AAPL 2025** — happy path 14.8s / $0.04 / 23 items, with 5 IBR resolved from DEF 14A
5. **`/eval/run` live** — interviewer sees 18-case suite pass on real SEC data

### Task 1 demo

```bash
# lint-and-test on a real GitHub repo
echo '{"repo_url":"https://github.com/dgunning/edgartools","ref":"main","lint_only":true}' \
  | python .claude/skills/lint-and-test/scripts/run.py

# build-and-release dry run
echo '{"repo_url":"https://github.com/dgunning/edgartools","version_bump":"minor","dry_run":true}' \
  | python .claude/skills/build-and-release/scripts/run.py
```

### Task 2 demo

```bash
# Cookies-based Gemini, no API key required
echo '{"task":"Go to example.com and report the page title","max_steps":5,"headless":true}' \
  | python .claude/skills/browse-execute-task/scripts/run.py
```

## Reference repos (in `_references/`, gitignored)

We surveyed the agent ecosystem and **borrow patterns, not dependencies** (only `browser-use` is a hard dep):

- `MetaClaw` (aiming-lab) — self-evolving agent, Contexture cross-session memory
- `AutoHarness` (aiming-lab) — 6-step governance pipeline, YAML constitution
- `OpenHarness` (HKUDS) — open agent harness "Ohmo"
- `hermes-agent` (Nous Research) — three-layer memory + auto skill generation
- `openclaw` — viral 2026 personal AI agent (first-class Skills)
- `browser-use` — DOM-first browser agent (90k stars; the only hard dep)
- `skyvern`, `LaVague` — Task 2 alternatives we evaluated
- `edgartools`, `edgar-crawler` — Task 3 SEC tooling references
- `anthropic-cookbook`, `modelcontextprotocol/servers` — MCP / Skills patterns

See `../INTEGRATION_REFERENCES.md` for the concept-to-package mapping.

## Project documents

Top-level (in repo root):

| File | Purpose |
|---|---|
| `AI-Coding-Test-EN.md` / `-ZH.md` | Original interview spec |
| `PLAN_v0.2.md` | Initial gap analysis vs spec, 7-question matrix |
| `EXECUTION_BLUEPRINT.md` | Per-stage IO blueprint with sample traces |
| `FLEXIBILITY_PRINCIPLE.md` | Design philosophy (Tier A/B/C) |
| `IO_CONTRACTS.md` | Tightened contracts after Gemini critique |
| `CRITIQUE_RESPONSE.md` | Synthesis of Gemini Round 1-3 critique |
| `THREE_TASKS_EXPLAINED.md` | Plain-language IO walkthrough per task |
| `CONSULTING_REPORT.md` | Management-style status update |
| `INTEGRATION_REFERENCES.md` | Borrowed-pattern map |

## License

MIT (intended for portfolio).

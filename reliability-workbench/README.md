# Reliability Workbench

> Unified platform for 3 AI Coding Test tasks: **CI/CD Skills**, **Browser Agent**, **SEC 10-K Extractor**.
> Three apps share one core (LLM routing, eval, observability, cost). One Zeabur deployment, three endpoints.

## Why a single platform?

Three tasks look different but share structure: **messy real-world input → LLM judgment + rules → clean structured output + confidence + cost trace**. Building the boring shared parts once means each app is thin and the eval discipline is uniform across all three.

## Layout

```
reliability-workbench/
├── packages/                 # Shared core. Apps depend ONLY on this.
│   ├── llm_router/           # Claude / Gemini / Ollama + cost cap + cache
│   ├── eval_kit/             # Suite runner, scorers, calibration check
│   ├── skills_registry/      # SKILL.md loader (agentskills.io compatible)
│   ├── session_manager/      # cookies, rate limit, TLS impersonation
│   ├── doc_parser/           # HTML / iXBRL / plaintext / PDF unified
│   ├── cost_ledger/          # SQLite per-call ledger; budget enforcement
│   ├── prompt_registry/      # versioned prompts with frontmatter
│   ├── sandbox/              # subprocess / Docker for arbitrary code exec
│   ├── confidence/           # logprob / consensus / self-eval; calibration
│   ├── observability/        # trace writer; replay
│   └── service_base/         # FastAPI base, Zeabur Dockerfile template
│
├── apps/                     # Task implementations. Self-contained.
│   ├── cicd-skills/          # Task 1: GitHub CI as Claude Skills
│   ├── browser-agent/        # Task 2: NL → browser actions, self-correcting
│   └── sec10k-extractor/     # Task 3: 10-K → item-level structured JSON
│
├── .claude/skills/           # All Skills live here (project layer)
│   └── _template/SKILL.md    # canonical template
│
├── prompts/                  # aggregated prompt records (per spec requirement)
├── infra/zeabur/             # deployment manifest
└── tests/                    # cross-package integration tests
```

## Decoupling rules (so future agents can maintain)

1. **One-way dependency**: `apps/* → packages/*` only. **Apps never import each other.**
2. **Self-contained apps**: each app has its own README, prompts/, evals/, src/, Dockerfile.
3. **Thin core**: `packages/` contains no domain logic. Domain stuff (10-K rules, browser strategies) lives in apps/.
4. **Module docstring contract**: every package's `__init__.py` documents *what I do / don't do / my IO contract / my hidden facts*. Agents read docstrings, not implementation.

## Flexibility principle (FLEXIBILITY_PRINCIPLE.md)

Rules are the **fast path** (~ms, $0). LLM is the **safety net** (~s, ~$0.01). Three tiers per task:

```
Tier A rules → candidates + per-candidate confidence
Tier B LLM   → confirm + supplement when rules uncertain
Tier C cross-check → final confidence (XBRL match, multi-model consensus)
```

Failure never raises — only lowers confidence. `confidence < 0.7` → `needs_review`, never silent guess.

## How to run

```bash
# Setup
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev,browser]"

# Local run (single gateway)
uvicorn apps.gateway:app --reload --port 8000

# Run an eval suite
python -m packages.eval_kit run apps/sec10k-extractor/evals/golden.jsonl

# Run a single skill
curl -X POST http://localhost:8000/skills/10k-extract-structured \
  -d '{"cik":"0000320193","accession":"0000320193-25-000079"}'
```

## Status

- [x] Day 0: Skeleton + reference repos cloned (10 in `/_references/`) + 10-K seed corpus (10 companies, 53 MB)
- [ ] Day 1-3: packages/llm_router + cost_ledger + eval_kit functional
- [ ] Day 4-8: apps/sec10k-extractor (Task 3 deep)
- [ ] Day 9-13: apps/browser-agent (Task 2 deep)
- [ ] Day 14-17: apps/cicd-skills + cross-task CI
- [ ] Day 18-21: eval rigor (drift_canary + adversarial generator)
- [ ] Day 22-25: meta-skills (prompt-evolve, skill-from-trace)
- [ ] Day 26-28: Zeabur deploy + dashboard
- [ ] Day 29-30: buffer / polish / interview prep

## Reference docs

- `../EXECUTION_BLUEPRINT.md` — full per-stage IO + sample traces
- `../FLEXIBILITY_PRINCIPLE.md` — design philosophy
- `../PLAN_v0.2.md` — gap analysis vs spec
- `../TALK_v1.md`, `../TALK_v2.md` — design conversations

# Integration References — MetaClaw / AutoHarness / Hermes / OpenHarness / browser-use

> 2026-04-28 · Per William's request to put these into our pipeline + decoupled
>
> **Strategy: borrow patterns, not dependencies.** Each external repo lives in `_references/`
> read-only. Our code in `reliability-workbench/` may take inspiration but doesn't import them.

---

## §1 What we have on disk now

| Repo | Size | Status | Why we have it |
|---|---|---|---|
| `_references/MetaClaw/` | 99 MB | New | aiming-lab — self-evolving agent + Contexture memory |
| `_references/AutoHarness/` | 21 MB | New | aiming-lab — "agent = model + harness", 6-step governance |
| `_references/OpenHarness/` | 23 MB | New | HKUDS — open agent harness "Ohmo" |
| `_references/awesome-harness-engineering/` | 0.7 MB | New | curated reading list |
| `_references/hermes-agent/` | 59 MB | Existing | Nous Research — three-layer memory + skill auto-gen |
| `_references/openclaw/` | 213 MB | Existing | viral 2026 personal AI agent |
| `_references/OpenClaw-RL/` | 69 MB | Existing | RL trajectory format |
| `_references/browser-use/` | 13 MB | Existing | Task 2 baseline |
| `_references/skyvern/` | 830 MB | Existing | Task 2 vision-first alternative |
| `_references/LaVague/` | 120 MB | Existing | Task 2 NL→action compiler |
| `_references/edgartools/` | 1.8 GB | Existing | Task 3 EDGAR Python lib |
| `_references/edgar-crawler/` | 91 MB | Existing | Task 3 Item heuristics |
| `_references/anthropic-cookbook/` | 352 MB | Existing | Skills + Claude best practices |

Total reference disk: ~3.6 GB. **Zero of these are imported as dependencies of `reliability-workbench/`.**

---

## §2 Conceptual mapping (their concept → our package)

### MetaClaw (aiming-lab)

| MetaClaw concept | Our analogue | Borrow what? |
|---|---|---|
| Skills mode (skills injected per turn) | `packages/skills_registry/` + `.claude/skills/` | Already aligned (agentskills.io standard) |
| RL mode (continual learning from real conversations) | (future) Tier 5 meta-skills | **Inspires**: capture trace → derive new skill candidates |
| Auto mode (skills + scheduled RL) | (future) `prompt-evolve` meta-skill | **Inspires**: weekly cron that re-runs eval, updates prompt |
| Contexture layer (cross-session memory, auto retrieval) | `packages/prompt_registry/` (current scope) | **Borrow**: idea of automatic memory retrieval per turn (defer to v0.2) |
| Multi-claw support (OpenClaw / IronClaw / PicoClaw / etc.) | `packages/llm_router/` providers | **Already aligned**: each provider isolated |
| OpenClaw extension (drop-in plugin) | `.claude/skills/` directory layout | **Already aligned** |

### AutoHarness (aiming-lab — same lab)

| AutoHarness concept | Our analogue | Borrow what? |
|---|---|---|
| `AutoHarness.wrap(OpenAI())` 2-line governance | `LLMRouter.call_with_fallback(...)` | **Already aligned**, ours is more explicit |
| 3-tier pipeline (Core / Standard / Enhanced) | Our 3-tier flexibility (rules / LLM / cross-check) | **Different axes** — theirs is governance depth, ours is reliability tiers |
| 6-step governance pipeline | `cost_ledger.enforce_budget` + sandbox checks | **Borrow**: explicit 6 named steps (input → policy → cost → execute → audit → output) |
| Risk pattern matching | Future security skill | **Borrow**: regex-based + LLM-classified risk patterns |
| YAML constitution | (none yet) | **Borrow**: `policy.yaml` per task — declares allowed tools, budgets, escalation |
| Trace-based diagnostics | `packages/observability/` | **Already aligned** |
| Cost tracking | `packages/cost_ledger/` | **Already aligned** |
| Multi-agent profiles | Per-skill input/output schemas | **Already aligned** |
| Session persistence | `_traces/<id>.jsonl` | **Already aligned** |

→ AutoHarness is **the closest peer to our architecture**. It's tempting to fork, but our pyproject is Python-pure, theirs has more deps. Read patterns, write our own.

### Hermes Agent (Nous Research)

| Hermes concept | Our analogue | Borrow what? |
|---|---|---|
| Three-layer memory (SOUL / MEMORY / USER) | `prompt_registry` versioning | **Borrow**: separation of persona / facts / preferences |
| Auto skill generation (after complex tasks) | (future) `skill-from-trace` meta-skill | **Borrow**: trace → diff against existing skills → propose new |
| FTS5 session search | (none yet) | **Defer**: SQLite FTS5 over `_traces/` for v0.2 |
| Skills Hub compatibility | `.claude/skills/` agentskills.io | **Already aligned** |
| Model independence (Nous Portal / OpenRouter / NIM / Kimi / MiniMax / HF / OpenAI) | `packages/llm_router/providers/` | **Already aligned** |
| 6 terminal backends (local/Docker/SSH/Daytona/Singularity/Modal) | `packages/sandbox/` (subprocess only) | **Borrow concept**: pluggable backend abstraction (already in our IO contract) |

### OpenHarness (HKUDS)

| OpenHarness concept | Our analogue | Borrow what? |
|---|---|---|
| Built-in personal agent "Ohmo" | (out of scope) | Skip |
| Agent harness wrapping LLM (eyes/hands/memory/safety) | Our packages collectively | **Already aligned** philosophically |

### browser-use (gregpr07 / browser-use)

| browser-use concept | Our analogue | Borrow what? |
|---|---|---|
| `Agent(task=, llm=).run_sync()` | `browse-execute-task/scripts/run.py` calls this directly | **Use as dependency** (only repo we actually call) |
| Action registry | (internal to browser-use) | Don't reimplement |
| DOM extraction | (internal to browser-use) | Don't reimplement |
| Their `skills/browser-use/SKILL.md` | (compatible format) | **Aligned** — ours plays nice with theirs |

---

## §3 Decoupled integration: what flows in, what stays out

### IN (we use directly as dep)

```
reliability-workbench/
└── pyproject.toml
    dependencies:
      - browser-use         # only via apps/.claude/skills/browse-execute-task
      - playwright          # required by browser-use
```

That's it. Everything else is reference-only.

### IN (we BORROW patterns from)

| Pattern | Source | Where in our code |
|---|---|---|
| Skill frontmatter format | OpenClaw + Hermes + browser-use SKILL.md (agentskills.io) | `.claude/skills/_template/SKILL.md` |
| 6-step governance | AutoHarness | (planned) `packages/llm_router/governance.py` |
| YAML constitution | AutoHarness | (planned) `policy.yaml` per app |
| Cross-session memory | MetaClaw Contexture + Hermes SOUL/MEMORY/USER | (deferred v0.2) `packages/prompt_registry/memory.py` |
| Drift report (no auto-patch) | Gemini critique reinforced by Hermes pattern | (in design) `apps/browser-agent/drift.py` |
| RL/skill evolution from traces | MetaClaw skills mode | (deferred v0.2) `skill-from-trace` meta-skill |

### OUT (we deliberately don't take)

- ❌ MetaClaw's RL training loop — out of scope (1-month interview project)
- ❌ AutoHarness's `wrap(OpenAI())` magic — too coupled to OpenAI; we have llm_router
- ❌ Hermes's CLI/messaging gateway — we have one FastAPI gateway
- ❌ OpenClaw's 22 messaging channels — not relevant
- ❌ Skyvern's full vision-first agent — overkill; browser-use enough

---

## §4 What this means for the demo

### Talking points the integration enables

1. **"agentskills.io standard"** — show that our SKILL.md is the same format as OpenClaw / Hermes / browser-use (interoperable in principle)
2. **"AutoHarness 6-step governance"** — borrow the framing for our LLM call governance (planned)
3. **"MetaClaw-inspired skill evolution"** — say we evaluated their pattern and **deferred** the auto-RL aspect, but the architecture supports it (we capture traces in JSONL — exactly the trajectory format)
4. **"3.6 GB of references read, none imported"** — discipline signal: we surveyed the space, picked a thin dependency surface, kept the core ours

### Anti-talking-points

- **We are NOT MetaClaw** (no RL)
- **We are NOT a personal assistant** (no messaging channels)
- **We are NOT a custom browser driver** (we use browser-use for that)

→ The 3 task implementations are domain-specific apps on a unified platform. The platform's design is informed by — but not derivative of — these other systems.

---

## §5 Concrete v0.2 backlog (from this integration analysis)

Items to add **after** the 3 tasks ship:

| # | Item | Source inspiration | Effort |
|---|---|---|---|
| 1 | `policy.yaml` per app (allowed tools, budgets, escalation) | AutoHarness | 1 day |
| 2 | `packages/llm_router/governance.py` (6-step pipeline) | AutoHarness | 2 days |
| 3 | `skill-from-trace` meta-skill (Hermes/MetaClaw style) | Hermes | 3 days |
| 4 | Cross-session memory in `prompt_registry` | MetaClaw Contexture | 4 days |
| 5 | FTS5 over `_traces/` for skill discovery | Hermes | 2 days |
| 6 | Multi-backend sandbox (Docker / Modal stubs) | Hermes (6 backends) | 3 days |

**These are NOT in the 30-day plan.** They're the natural follow-ons after interview submission.

---

## §6 Sources

- [aiming-lab/MetaClaw](https://github.com/aiming-lab/MetaClaw) — self-evolving agent
- [aiming-lab/AutoHarness](https://github.com/aiming-lab/AutoHarness) — agent governance harness
- [HKUDS/OpenHarness](https://github.com/HKUDS/OpenHarness) — open agent harness
- [ai-boost/awesome-harness-engineering](https://github.com/ai-boost/awesome-harness-engineering) — curated list
- [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) — self-improving agent (Nous Research)
- [openclaw/openclaw](https://github.com/openclaw/openclaw) — personal AI assistant
- [browser-use/browser-use](https://github.com/browser-use/browser-use) — browser agent (used as dep)
- [agentskills.io](https://agentskills.io) — open Skills standard

---

*v1.0 · 2026-04-28 · Reference survey + integration plan*

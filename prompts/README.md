# Prompts (per spec requirement)

> "在 repo 根目錄建 `prompts/` 資料夾保存主要 prompt — 我們會實際閱讀"
> — AI-Coding-Test-ZH §共通要求 #4

This folder collects the **actual prompts** used in production by our skills. Each is versioned and includes design notes.

## Layout

```
prompts/
├── README.md (this file — index)
├── 10k-confirm-items/        # Task 3 Tier B
│   ├── v1.md                 # First version (current)
│   └── EVOLUTION.md          # Why this prompt evolved
├── 10k-resolve-incorporation-section-locator/
│   └── v1.md                 # Find section in DEF 14A
├── browse-execute-task/      # Task 2 (delegated to browser-use)
│   └── README.md             # We don't own these prompts
└── design-conversations/     # Multi-round Gemini consultation logs
    ├── critique-blueprint.md
    ├── critique-io-contracts.md
    ├── strategy-7-day-sprint.md
    └── task-2-strategy.md
```

## Why these prompts matter to evaluation

1. **They show iteration**: each prompt has versions + a notes field documenting **why** that version came to be
2. **They show co-authoring with AI**: design-conversations/ shows raw Gemini critique that shaped them
3. **They show domain depth**: e.g. the 10-K confirm prompt encodes SEC item-status conventions explicitly, not as vague hints

## Where the running prompts live in code

Prompts are inlined in skill `scripts/run.py` files for execution speed (no file IO per call). The copies here are the **canonical record** for human review. We diff-check via `packages/prompt_registry/` (planned).

| Skill | Prompt location in code | Canonical copy here |
|---|---|---|
| `10k-confirm-items-llm` | `.claude/skills/10k-confirm-items-llm/scripts/run.py` `PROMPT_TEMPLATE` | `prompts/10k-confirm-items/v1.md` |
| `10k-resolve-incorporation` | `.claude/skills/10k-resolve-incorporation/scripts/run.py` `find_section_llm()` | `prompts/10k-resolve-incorporation-section-locator/v1.md` |
| `browse-execute-task` | (browser-use's internal Agent prompts) | not ours; `browse-execute-task/README.md` |

## Auto-aggregation

Future: when a skill's prompt changes, a CI hook re-syncs the canonical copy here. For now, manual.

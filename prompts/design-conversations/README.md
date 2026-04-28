# Design Conversations

Multi-round Gemini consultations that shaped the architecture. Each is a real co-design session with concrete code-level outputs.

| File | Topic | Outcome |
|---|---|---|
| [`critique-blueprint.md`](critique-blueprint.md) | Initial BLUEPRINT critique | Cost kill-switch, drift report (vs auto-patch), provenance metadata, 1990s ASCII A+++ killer |
| [`critique-io-contracts.md`](critique-io-contracts.md) | IO contract review (4 rounds) | TableBlock, raw_hash, max_file_size, output_schema validation, observability sanitizer |
| [`strategy-7-day-sprint.md`](strategy-7-day-sprint.md) | 7-day sprint plan check | Validated Task 3→1→2 order; "incorporation by reference" silent landmine; don't custom-build browser driver |
| [`task-2-strategy.md`](task-2-strategy.md) | Browser Agent design | Picked Option D Hybrid (browser-use as black-box engine + our verify/recover/drift layer); 7 sub-skill catalog; drift_report.json schema |

## Why include these in prompts/

The spec asks for prompt records "we will actually read". These multi-round conversations:
- **Show co-design with AI**, not just one-shot prompts
- **Document explicit tradeoffs** that shaped code (e.g., one-big-prompt vs per-item; we picked one-big after Round 3 reasoning)
- **Show our willingness to be told we're wrong** — Gemini Round 1 said "auto skill gen is hallucination", Round 2 retracted, we incorporated both views

Source files at `_sandbox/logs/gemini_*.md` in repo root (gitignored sandbox); these are stable canonical copies.

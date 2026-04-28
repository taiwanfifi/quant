---
name: skill-template
description: TEMPLATE — copy this directory to create a new skill. Replace this description with capability + trigger. e.g. "Extract X from Y. Use when user asks for X, mentions Y, or provides a Y URL."
---

# Skill Template

> Copy `_template/` → rename → fill out below. Compatible with [agentskills.io](https://agentskills.io) standard.

## What this skill does

One paragraph. What inputs it accepts, what outputs it produces. Concrete.

## When to use

Specific user phrasings that should trigger this skill:
- "..."
- "..."
- "..."

## Inputs

```json
{
  "field_name": "type — description",
  "optional_field": "string | null — default null"
}
```

Or reference `assets/input_schema.json`.

## Outputs

```json
{
  "result": "...",
  "confidence": "0.0-1.0",
  "trace_id": "string"
}
```

## How to invoke

1. Validate input against `assets/input_schema.json`
2. Run `python scripts/run.py <args>` (or import as module)
3. Validate output against `assets/output_schema.json`
4. Write trace via `packages.observability.trace.start/step/end`
5. Record cost via `packages.cost_ledger`

## Idempotency

Idempotency key: `sha256(<key fields>)`. Same input → same output (assuming no upstream API change).

## Failure modes

| Mode | Trigger | Handling |
|---|---|---|
| `input_invalid` | input fails schema | return 422-style error JSON |
| `upstream_error` | external API failed | retry with backoff (3x), then `needs_review` |
| `low_confidence` | rules + LLM both uncertain | return result with `confidence < 0.7` and `status: needs_review` |

## Cost & latency

- Typical: <X tokens, $Y, Zs>
- Worst case: ...

## References

- `references/edge_cases.md` — expanded failure handling
- `references/agentskills_compat.md` — what this skill exposes to OpenClaw / Hermes

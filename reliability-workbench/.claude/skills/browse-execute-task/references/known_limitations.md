# Known Limitations of `browse-execute-task`

## Multi-step planning requires structured-output LLM

Browser-use's Agent expects every LLM response to be a valid `AgentOutput` Pydantic
object containing a list of structured `Action` items. Three LLM paths support this
reliably:

| Path | Status | How |
|---|---|---|
| `ChatAnthropic` (with `ANTHROPIC_API_KEY`) | ✅ works | Claude has tool-use mode that guarantees schema compliance |
| `ChatGoogle` (with `GOOGLE_API_KEY`) | ✅ works | Gemini API has `response_schema` parameter |
| `ChatGeminiCookies` (our cookies-based fallback) | ⚠️ partial | Free-form text mode; we inject JSON-schema hints but Gemini cookies path doesn't guarantee strict adherence |

### Symptoms when cookies-Gemini fails

- Agent navigates to first URL (single-step works)
- On step 2+, browser-use raises `'str' object has no attribute 'action'`
- This means LLM returned plaintext instead of a parseable `AgentOutput` JSON

### Mitigations

1. **For real demos**: set `ANTHROPIC_API_KEY` (we already have llm_router compatibility)
2. **For free demos**: tasks that complete in 1 step may work (simple navigation)
3. **For zero-cost robust path** (planned v0.2): write a "browser-use lite" loop in our own
   skill that uses cookies-Gemini for plan/act with looser output validation

## What still works without API keys

- Stage 1 (browser launch + navigate to URL from task) ✅
- Result extraction from final URL state ✅  (the `url_visited` field is always populated)
- Cost = $0 (no API key cost)

## What requires API key

- Multi-step plans (filling forms, clicking through workflows)
- Self-correction across pages
- Drift report generation (requires comparing semantic outputs across attempts)

## Recommended demo path

For interview, set `ANTHROPIC_API_KEY` and use `model_preference="claude"` — claude-haiku
is fast (~3s/step), cheap (~$0.001/step), and natively supports tool-use schema.

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
echo '{"task":"Find latest stock price for NVDA on Google Finance","model_preference":"claude"}' \
  | python .claude/skills/browse-execute-task/scripts/run.py
```

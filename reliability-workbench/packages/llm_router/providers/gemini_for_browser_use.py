"""
Gemini cookies adapter for browser-use's LLM interface.

Why: browser-use ships with ChatGoogle (requires GOOGLE_API_KEY) and ChatAnthropic (requires
ANTHROPIC_API_KEY) but no out-of-the-box adapter for cookies-based Gemini. This module wraps
our self-contained gemini_cookies provider so browser-use can use it.

Usage:
  from packages.llm_router.providers.gemini_for_browser_use import ChatGeminiCookies
  from browser_use import Agent
  agent = Agent(task="...", llm=ChatGeminiCookies())
  result = await agent.run(max_steps=15)

Notes:
  - Uses our self-contained gemini_cookies provider (no external API key needed)
  - Token counts are estimated (cookies path doesn't return real counts)
  - Resets session on each Agent.run() to avoid carrying browser-use's prior context
"""
from __future__ import annotations

import json
from typing import Any

from . import gemini_cookies


class ChatGeminiCookies:
    """browser-use compatible chat client backed by cookies-based Gemini.

    browser-use's BaseChatModel interface (as of v0.11):
      - .ainvoke(messages, **kwargs) → ChatInvokeCompletion
      - .name property
      - .model property (used for cost tracking)
    """
    def __init__(self, *, model: str = "gemini-3-flash", reset_each_call: bool = False):
        self.model = model
        self.model_name = model            # browser-use checks .model_name in cloud_events
        self._reset_each_call = reset_each_call

    @property
    def name(self) -> str:
        return self.model

    @property
    def provider(self) -> str:
        return "gemini-cookies"

    async def ainvoke(self, messages: list, output_format=None, *args, **kwargs) -> Any:
        """Async invocation. browser-use calls .ainvoke(messages, output_format=schema).

        If output_format is provided, append a JSON-shape hint to the last user message
        so Gemini returns parseable JSON. The Pydantic-class output_format is best-effort.
        """
        if self._reset_each_call:
            gemini_cookies.reset_session()

        # If browser-use passed an output schema (a Pydantic model), inject a JSON hint
        json_hint = ""
        if output_format is not None:
            try:
                schema = output_format.model_json_schema()
                json_hint = (
                    f"\n\nReturn JSON matching this schema (no prose, no markdown fences):"
                    f"\n```json\n{json.dumps(schema)[:2000]}\n```"
                )
            except Exception:
                pass

        # Convert browser-use messages (which may be Pydantic objects or dicts) to plain dicts
        plain_messages = []
        for m in messages:
            if hasattr(m, "model_dump"):
                d = m.model_dump()
            elif hasattr(m, "dict"):
                d = m.dict()
            elif isinstance(m, dict):
                d = m
            else:
                d = {"role": "user", "content": str(m)}

            role = d.get("role", "user")
            content = d.get("content", "")
            if isinstance(content, list):
                # OpenAI-style content array → flatten text parts
                content = "\n".join(
                    p.get("text", "") if isinstance(p, dict) else str(p)
                    for p in content
                )
            plain_messages.append({"role": role, "content": str(content)})

        # Append JSON shape hint to last user message if output_format was given
        if json_hint and plain_messages:
            for i in range(len(plain_messages) - 1, -1, -1):
                if plain_messages[i]["role"] == "user":
                    plain_messages[i]["content"] += json_hint
                    break

        text, tokens_in, tokens_out, raw = gemini_cookies.call(
            messages=plain_messages,
            model=self.model,
            temperature=0,
        )

        # If output_format was a Pydantic model, parse the JSON and instantiate
        parsed_completion = text
        if output_format is not None:
            try:
                # Strip markdown fences if any
                stripped = text.strip()
                m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", stripped)
                if m:
                    stripped = m.group(1)
                else:
                    m2 = re.search(r"\{[\s\S]*\}", stripped)
                    if m2:
                        stripped = m2.group(0)
                data = json.loads(stripped)
                if hasattr(output_format, "model_validate"):
                    parsed_completion = output_format.model_validate(data)
                elif hasattr(output_format, "parse_obj"):
                    parsed_completion = output_format.parse_obj(data)
            except Exception:
                pass  # fallback to raw text

        # Wrap into a structure browser-use expects.
        # browser-use's ChatInvokeCompletion has: completion, usage, raw
        try:
            from browser_use.llm.views import ChatInvokeCompletion, ChatInvokeUsage
            usage = ChatInvokeUsage(
                prompt_tokens=tokens_in,
                completion_tokens=tokens_out,
                total_tokens=tokens_in + tokens_out,
                prompt_cached_tokens=0,
                prompt_cache_creation_tokens=0,
                prompt_image_tokens=0,
            )
            return ChatInvokeCompletion(
                completion=parsed_completion,
                usage=usage,
                raw=raw,
            )
        except (ImportError, AttributeError):
            # Fallback: return plain dict that mimics structure
            return {
                "completion": text,
                "usage": {"prompt_tokens": tokens_in,
                            "completion_tokens": tokens_out,
                            "total_tokens": tokens_in + tokens_out},
                "raw": raw,
            }

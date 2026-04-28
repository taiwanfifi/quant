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

    async def ainvoke(self, messages: list, **kwargs) -> Any:
        """Async invocation. Converts browser-use message list to our prompt format."""
        if self._reset_each_call:
            gemini_cookies.reset_session()

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

        text, tokens_in, tokens_out, raw = gemini_cookies.call(
            messages=plain_messages,
            model=self.model,
            temperature=0,
        )

        # Wrap into a structure browser-use expects.
        # browser-use's ChatInvokeCompletion has: completion, usage, raw
        try:
            from browser_use.llm.views import ChatInvokeCompletion, ChatInvokeUsage
            usage = ChatInvokeUsage(
                prompt_tokens=tokens_in,
                completion_tokens=tokens_out,
                total_tokens=tokens_in + tokens_out,
            )
            return ChatInvokeCompletion(
                completion=text,
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

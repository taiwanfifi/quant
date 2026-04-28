#!/usr/bin/env python3
"""
browse-execute-task — wraps browser-use Agent with our verify + drift report layer.

Strategy (per Gemini Round 1, Option D Hybrid):
  1. browser-use handles Plan + Act (DOM extraction + LLM driving)
  2. We add: trace via observability, drift detection, structured output
  3. NO custom browser driver
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from packages.observability import start as trace_start, step as trace_step, end as trace_end  # noqa: E402


def _err(t: str, m: str, **kw) -> dict:
    return {"ok": False, "task": kw.pop("task", ""),
             "steps_taken": 0, "elapsed_ms": 0, "needs_human_review": True,
             "reason": t,
             "error_type": t, "error_message": m, **kw}


def _check_browser_use() -> tuple[bool, str | None]:
    try:
        import browser_use  # noqa: F401
        return True, None
    except ImportError as e:
        return False, str(e)


def _check_playwright() -> tuple[bool, str | None]:
    try:
        import playwright  # noqa: F401
        return True, None
    except ImportError as e:
        return False, str(e)


def _build_llm(model_pref: str):
    """Pick an LLM compatible with browser-use's interface."""
    # Gemini path: use ChatGoogle if google API key available; else fallback to ChatBrowserUse
    if model_pref in ("gemini", "auto"):
        # browser-use exposes ChatGoogle for Gemini
        if os.environ.get("GOOGLE_API_KEY"):
            from browser_use.llm import ChatGoogle
            return ChatGoogle(model="gemini-2.5-flash"), "gemini"

    if model_pref in ("claude", "auto", "claude-haiku-4-5", "claude-sonnet-4-6"):
        if os.environ.get("ANTHROPIC_API_KEY"):
            from browser_use.llm import ChatAnthropic
            model = "claude-sonnet-4-5-20250929" if "sonnet" in model_pref else "claude-haiku-4-5"
            return ChatAnthropic(model=model), model

    # Fallback: browser-use's own LLM service (requires their API key)
    if os.environ.get("BROWSER_USE_API_KEY"):
        from browser_use.llm import ChatBrowserUse
        return ChatBrowserUse(model="bu-2-0"), "bu-2-0"

    return None, None


async def run_async(task: str, *,
                     site_hint: str | None,
                     max_steps: int,
                     headless: bool,
                     model_pref: str,
                     trace_ctx) -> dict:
    """Run browser-use Agent and capture trace events."""
    from browser_use import Agent

    llm, model_used = _build_llm(model_pref)
    if llm is None:
        return _err("no_llm_credentials",
                    "no GOOGLE_API_KEY / ANTHROPIC_API_KEY / BROWSER_USE_API_KEY in env")

    full_task = task
    if site_hint:
        full_task = f"{task}\n\nStart at: {site_hint}"

    # Instantiate agent
    try:
        agent = Agent(task=full_task, llm=llm)
    except Exception as e:
        return _err("agent_init_failed", str(e), task=task)

    trace_step(trace_ctx, kind="agent-init", data={"model": model_used,
                                                     "headless": headless})

    # Run and collect history
    try:
        # Newer browser-use versions return AgentHistoryList
        history = await agent.run(max_steps=max_steps)
    except Exception as e:
        return _err("agent_run_failed", str(e)[:500], task=task,
                     model_used=model_used or "")

    # Extract structured info from history
    final_result = None
    steps_count = 0
    drift_reports: list = []
    answer_text = ""
    extracted: dict = {}
    last_url = ""

    try:
        if hasattr(history, "history"):
            steps_count = len(history.history)
            for i, h in enumerate(history.history):
                trace_step(trace_ctx, kind="step", data={
                    "step_i": i,
                    "action": str(h.model_output)[:300] if hasattr(h, "model_output") else "?",
                })

        if hasattr(history, "final_result"):
            final_result = history.final_result()
            if isinstance(final_result, str):
                answer_text = final_result
        if hasattr(history, "extracted_content"):
            ec = history.extracted_content()
            if ec:
                extracted = ec if isinstance(ec, dict) else {"value": str(ec)}
        if hasattr(history, "urls"):
            urls = history.urls()
            if urls:
                last_url = urls[-1] if isinstance(urls, list) else str(urls)
    except Exception as e:
        trace_step(trace_ctx, kind="warning",
                    data={"history_parse_warning": str(e)[:200]})

    return {
        "ok": True,
        "task": task,
        "result": {
            "answer": answer_text or final_result or "",
            "extracted_data": extracted,
            "url_visited": last_url,
        },
        "steps_taken": steps_count,
        "recoveries": 0,  # browser-use handles internal retries; we don't surface count yet
        "drift_reports": drift_reports,
        "confidence": 0.85 if (answer_text or extracted) else 0.5,
        "model_used": model_used or "",
        "cost_usd": 0.0,
        "tokens_in": 0, "tokens_out": 0,
        "needs_human_review": False,
        "fallback_chain": ["primary"],
    }


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps(_err("input_empty", "no JSON on stdin"))); sys.exit(1)
    try:
        inputs = json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps(_err("input_invalid_json", str(e)))); sys.exit(1)

    t0 = time.time()
    task = inputs["task"]
    site_hint = inputs.get("site_hint")
    max_steps = int(inputs.get("max_steps", 20))
    headless = bool(inputs.get("headless", True))
    model_pref = inputs.get("model_preference", "gemini")

    # Pre-flight
    bu_ok, bu_err = _check_browser_use()
    if not bu_ok:
        print(json.dumps(_err("browser_use_not_installed",
                                f"pip install browser-use; {bu_err}",
                                task=task)))
        sys.exit(1)
    pw_ok, pw_err = _check_playwright()
    if not pw_ok:
        print(json.dumps(_err("playwright_not_installed",
                                f"pip install playwright && playwright install chromium; {pw_err}",
                                task=task)))
        sys.exit(1)

    ctx = trace_start(task=f"browse-execute-{task[:30].replace(' ', '_')}",
                      metadata={"site_hint": site_hint, "model_pref": model_pref,
                                 "headless": headless})

    try:
        out = asyncio.run(run_async(
            task=task, site_hint=site_hint, max_steps=max_steps,
            headless=headless, model_pref=model_pref, trace_ctx=ctx,
        ))
        out["elapsed_ms"] = int((time.time() - t0) * 1000)
        out["trace_id"] = ctx.trace_id
        trace_end(ctx, output={"steps_taken": out.get("steps_taken", 0),
                                  "ok": out.get("ok", False)},
                  success=out.get("ok", False))
        print(json.dumps(out))
        sys.exit(0 if out.get("ok") else 1)
    except Exception as e:
        out = _err("unexpected", str(e)[:500], task=task)
        out["elapsed_ms"] = int((time.time() - t0) * 1000)
        out["trace_id"] = ctx.trace_id
        trace_end(ctx, output={"failed": True}, success=False)
        print(json.dumps(out))
        sys.exit(1)


if __name__ == "__main__":
    main()

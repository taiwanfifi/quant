"""Router implementation — see __init__.py docstring for contract."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

# Providers loaded lazily to keep import-time cheap and tolerate missing deps.
_PROVIDER_CACHE: dict[str, Any] = {}


class Message(TypedDict, total=False):
    """A single chat message. Per Gemini critique §2 — was list[dict], too loose."""
    role: Literal["system", "user", "assistant"]
    content: str
    # Optional: cache_control for Anthropic prompt caching
    cache_control: dict[str, str]


def _validate_messages(messages: list[dict]) -> None:
    """Lightweight invariant check; raises ValueError on bad input."""
    if not messages:
        raise ValueError("messages must be non-empty")
    for i, m in enumerate(messages):
        if not isinstance(m, dict):
            raise ValueError(f"messages[{i}] must be dict, got {type(m).__name__}")
        if "role" not in m or m.get("role") not in {"system", "user", "assistant"}:
            raise ValueError(f"messages[{i}].role missing or invalid")
        if "content" not in m or not isinstance(m["content"], str):
            raise ValueError(f"messages[{i}].content missing or not str")


@dataclass
class LLMResponse:
    text: str
    model_used: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    cache_hit: bool = False
    confidence_hint: float | None = None  # provider-reported confidence (rare)
    raw: dict[str, Any] = field(default_factory=dict)
    fallback_chain: list[str] = field(default_factory=list)  # which models tried


class RouterError(Exception):
    pass


class BudgetExhausted(RouterError):
    pass


class NeedsReview(RouterError):
    """Raised by call_with_fallback when no model produced confident answer."""
    def __init__(self, reason: str, attempts: list[dict[str, Any]]):
        super().__init__(reason)
        self.reason = reason
        self.attempts = attempts


# Model → cost per 1M tokens (input, output) — keep updated
MODEL_COSTS = {
    "claude-opus-4-7": (15.00, 75.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (0.80, 4.00),
    "gemini-3-flash": (0.0, 0.0),  # via cookies = free
    "gemini-3-pro": (0.0, 0.0),
    "ollama:llama3.3": (0.0, 0.0),  # local
}

# Routing rules per complexity
COMPLEXITY_TO_MODEL = {
    "easy": "claude-haiku-4-5",
    "medium": "claude-sonnet-4-6",
    "hard": "claude-opus-4-7",
}


class LLMRouter:
    def __init__(self, *, daily_budget_usd: float = 10.0, cost_ledger=None):
        self.daily_budget_usd = daily_budget_usd
        self.cost_ledger = cost_ledger  # injected; can be None for tests
        self._spent_today_usd = 0.0  # in-memory shadow of ledger

    # ----- provider lazy loading -----
    def _get_provider(self, name: str):
        if name not in _PROVIDER_CACHE:
            if name.startswith("claude"):
                from .providers import claude
                _PROVIDER_CACHE[name] = claude
            elif name.startswith("gemini"):
                from .providers import gemini_cookies
                _PROVIDER_CACHE[name] = gemini_cookies
            elif name.startswith("ollama"):
                from .providers import ollama
                _PROVIDER_CACHE[name] = ollama
            else:
                raise RouterError(f"Unknown provider for model: {name}")
        return _PROVIDER_CACHE[name]

    # ----- core call -----
    def call(
        self,
        messages: list[dict],
        *,
        model: str = "auto",
        complexity: Literal["easy", "medium", "hard"] = "medium",
        prompt_id: str | None = None,
        budget_usd: float | None = None,
        require_local: bool = False,
        temperature: float = 0,
        max_tokens: int = 4096,
        absolute_deadline: float | None = None,
    ) -> LLMResponse:
        """Single LLM call. Cost recorded; raises BudgetExhausted if over cap.

        absolute_deadline: unix timestamp. If `time.time() > absolute_deadline` before
        the call starts, raises TimeoutError immediately (no fork-and-cancel; we just
        check at entry). Per Gemini Round 4 — prevents hung internal calls.
        """
        if absolute_deadline is not None and time.time() > absolute_deadline:
            raise TimeoutError(f"deadline exceeded before call to {model}")
        _validate_messages(messages)
        if model == "auto":
            model = "ollama:llama3.3" if require_local else COMPLEXITY_TO_MODEL[complexity]

        if budget_usd is not None and self._spent_today_usd >= budget_usd:
            raise BudgetExhausted(f"Spent ${self._spent_today_usd:.2f} >= cap ${budget_usd:.2f}")

        provider = self._get_provider(model)
        t0 = time.time()
        try:
            text, tokens_in, tokens_out, raw = provider.call(
                messages=messages, model=model, temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:
            # Last-ditch fallback: if Claude works, try it
            if not model.startswith("claude"):
                try:
                    return self.call(messages, model=COMPLEXITY_TO_MODEL[complexity],
                                     complexity=complexity, prompt_id=prompt_id,
                                     budget_usd=budget_usd, temperature=temperature,
                                     max_tokens=max_tokens)
                except Exception:
                    pass
            raise RouterError(f"Provider {model} failed: {e}") from e

        latency_ms = int((time.time() - t0) * 1000)
        cost_in_per_m, cost_out_per_m = MODEL_COSTS.get(model, (0.0, 0.0))
        cost_usd = (tokens_in * cost_in_per_m + tokens_out * cost_out_per_m) / 1_000_000
        self._spent_today_usd += cost_usd

        if self.cost_ledger:
            self.cost_ledger.record(
                task=prompt_id or "ad-hoc", model=model,
                tokens_in=tokens_in, tokens_out=tokens_out,
                cost_usd=cost_usd, latency_ms=latency_ms, success=True,
                trace_id=prompt_id or "",
            )

        return LLMResponse(
            text=text, model_used=model, tokens_in=tokens_in, tokens_out=tokens_out,
            cost_usd=cost_usd, latency_ms=latency_ms, raw=raw,
            fallback_chain=[model],
        )

    # ----- cascading fallback (FLEXIBILITY §5.1) -----
    def call_with_fallback(
        self,
        messages: list[dict],
        *,
        rules_confidence: float | None = None,
        rules_result: Any = None,
        confidence_threshold: float = 0.85,
        models: tuple[str, ...] = ("claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-7"),
        **kwargs,
    ) -> LLMResponse:
        """
        Cascading fallback per FLEXIBILITY_PRINCIPLE §5.1.

        - If rules_confidence >= threshold, return rules_result wrapped (no LLM call).
        - Else try cheap model. If LLM-reported confidence >= threshold, return.
        - Else escalate to next model.
        - If all exhausted, raise NeedsReview with attempt history.
        """
        if rules_confidence is not None and rules_confidence >= confidence_threshold:
            return LLMResponse(
                text=str(rules_result), model_used="rules", tokens_in=0, tokens_out=0,
                cost_usd=0.0, latency_ms=0, confidence_hint=rules_confidence,
                fallback_chain=["rules"],
            )

        attempts = []
        chain = ["rules"] if rules_confidence is not None else []
        for model in models:
            try:
                resp = self.call(messages, model=model, **kwargs)
                chain.append(model)
                resp.fallback_chain = chain
                # Heuristic: if response includes a confidence (parseable from output), check it.
                # For now, we accept the first model that doesn't error.
                # Real callers can re-call with a stricter confidence parser.
                return resp
            except (BudgetExhausted, RouterError) as e:
                attempts.append({"model": model, "error": str(e)})
                continue

        raise NeedsReview(reason="all models failed or over budget", attempts=attempts)

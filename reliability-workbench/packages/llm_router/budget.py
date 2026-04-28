"""
Task Budget & Cost Kill-Switch — per Gemini critique Round 3 ADD-C.

WHAT I DO:
  - Hard cap per task (default $1 / 500K tokens)
  - At 80% of cap: auto-downgrade requests to cheap model (haiku)
  - At 100% of cap: refuse further calls (raise KillSwitchTriggered)

WHY:
  - Demonstrates "economic discipline" — quants care about P&L
  - Prevents accidental $5000 API bills from a runaway loop

USAGE:
  budget = TaskBudget(task="sec10k-extract", max_usd=1.0, max_tokens=500_000)
  while budget.has_room():
      model = budget.select_model(requested="claude-sonnet-4-6")
      ...
      budget.charge(cost_usd=0.04, tokens=12000)
"""
from __future__ import annotations

from dataclasses import dataclass, field


class KillSwitchTriggered(RuntimeError):
    pass


@dataclass
class TaskBudget:
    task: str
    max_usd: float = 1.0
    max_tokens: int = 500_000
    downgrade_threshold: float = 0.8        # 80% of cap → force cheap model
    downgrade_target: str = "claude-haiku-4-5"
    spent_usd: float = 0.0
    used_tokens: int = 0
    downgrade_events: list[dict] = field(default_factory=list)

    @property
    def usd_pct(self) -> float:
        return self.spent_usd / self.max_usd if self.max_usd > 0 else 0.0

    @property
    def token_pct(self) -> float:
        return self.used_tokens / self.max_tokens if self.max_tokens > 0 else 0.0

    @property
    def at_threshold(self) -> bool:
        return self.usd_pct >= self.downgrade_threshold or self.token_pct >= self.downgrade_threshold

    @property
    def at_cap(self) -> bool:
        return self.usd_pct >= 1.0 or self.token_pct >= 1.0

    def has_room(self) -> bool:
        return not self.at_cap

    def select_model(self, requested: str) -> str:
        """Returns the model to actually use; force-downgrade if past threshold."""
        if self.at_cap:
            raise KillSwitchTriggered(
                f"Task '{self.task}' hit cap: ${self.spent_usd:.2f}/{self.max_usd} or "
                f"{self.used_tokens}/{self.max_tokens} tokens"
            )
        if self.at_threshold and not requested.endswith("haiku-4-5"):
            self.downgrade_events.append({
                "requested": requested, "downgraded_to": self.downgrade_target,
                "spent_usd": self.spent_usd, "used_tokens": self.used_tokens,
            })
            return self.downgrade_target
        return requested

    def charge(self, *, cost_usd: float, tokens: int):
        self.spent_usd += cost_usd
        self.used_tokens += tokens

    def summary(self) -> dict:
        return {
            "task": self.task,
            "spent_usd": round(self.spent_usd, 4),
            "max_usd": self.max_usd,
            "used_tokens": self.used_tokens,
            "max_tokens": self.max_tokens,
            "usd_pct": round(self.usd_pct, 3),
            "token_pct": round(self.token_pct, 3),
            "downgrade_count": len(self.downgrade_events),
        }

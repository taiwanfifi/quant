"""
Eval Kit — run evaluation suites against a runner function.

WHAT I DO:
  - Load .jsonl suite files
  - Execute a runner(input) → output for each case
  - Apply scorers (per-case + invariants)
  - Aggregate report (accuracy, cost, latency, failure_modes, calibration)

WHAT I DON'T DO:
  - I don't know about your task domain — runner is caller-supplied
  - I don't generate adversarial cases (that's eval_generator, separate package)
  - I don't decide "good enough" — caller compares accuracy to spec

IO CONTRACT:
  EvalCase(id, input, expected, invariants, metadata)
  Scorer.score(output, expected, invariants) → dict[str, float]
  EvalKit.run(suite_path, runner, scorers, budget_usd) → EvalReport

HIDDEN FACTS:
  - Each run gets its own report ID; accumulate over time for drift detection
  - Runner can return {"output": ..., "confidence": ...} — confidence is preserved for calibration
  - Budget enforced via cost_ledger if injected
"""

from .runner import EvalKit, EvalCase, EvalResult, EvalReport
from .scorers import (
    Scorer, ExactMatchScorer, StructuralScorer, InvariantScorer
)

__all__ = [
    "EvalKit", "EvalCase", "EvalResult", "EvalReport",
    "Scorer", "ExactMatchScorer", "StructuralScorer", "InvariantScorer",
]

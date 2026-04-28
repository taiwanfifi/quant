"""
Confidence — estimate + calibrate per-output confidence scores.

WHAT I DO:
  - Compute confidence from multiple signals: rule strength, LLM consensus,
    invariant satisfaction, XBRL cross-validation
  - Aggregate signals into a single 0-1 score with documented weights
  - Calibration check: bin observations by claimed confidence → verify actual
    accuracy matches (Expected Calibration Error / ECE)

WHAT I DON'T DO:
  - I don't know your task domain; signals are caller-supplied dicts
  - I don't call LLMs (consensus inputs are precomputed by caller)
  - I don't store history (caller stores eval results; I just compute)

IO CONTRACT:
  ConfidenceEstimator()
    .from_signals(signals: dict[str, float], weights: dict[str, float] | None) → float
    .from_consensus(outputs: list[Any], comparator: Callable | None) → float
    .calibrate(eval_results: list[dict]) → CalibrationReport

  CalibrationReport(ece: float, bins: list[BinStat], n: int, well_calibrated: bool)

HIDDEN FACTS:
  - Default weights bias toward XBRL match (highest signal) and rule strength;
    LLM consensus is moderate (because LLMs can be confidently wrong together)
  - ECE > 0.1 → caller's confidence is poorly calibrated (we don't fix it,
    just report)
  - from_consensus on nested dicts uses fuzzy match (not strict ==) to avoid
    Gemini Round 3's overfit warning
"""

from .estimator import (
    ConfidenceEstimator,
    CalibrationReport,
    BinStat,
    DEFAULT_WEIGHTS,
)

__all__ = ["ConfidenceEstimator", "CalibrationReport", "BinStat", "DEFAULT_WEIGHTS"]

"""ConfidenceEstimator implementation."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable


# Per Gemini Round 1 critique: weights bias toward objective signals (XBRL,
# rule strength) over subjective ones (LLM consensus, which can be confidently wrong)
DEFAULT_WEIGHTS = {
    "rules_strength": 0.30,        # rules pattern confidence (0.40-0.95 typical)
    "llm_consensus": 0.20,         # multi-model agreement
    "invariants_passed": 0.25,     # how many invariants satisfied (schema, ordering, ranges)
    "cross_validation": 0.25,      # XBRL match for SEC; URL+title match for browser
}


@dataclass
class BinStat:
    bin_low: float
    bin_high: float
    n: int
    avg_claimed_confidence: float | None
    actual_accuracy: float | None


@dataclass
class CalibrationReport:
    ece: float                    # Expected Calibration Error (0-1; lower = better)
    bins: list[BinStat]
    n: int                        # total samples with confidence + accuracy
    well_calibrated: bool         # ece < 0.1 threshold


def _fuzzy_eq(a: Any, b: Any, *, threshold: float = 0.9) -> bool:
    """Fuzzy comparison for consensus. Strings: substring or hi-overlap. Dicts: same keys + recursive."""
    if a == b:
        return True
    if isinstance(a, str) and isinstance(b, str):
        a_l, b_l = a.strip().lower(), b.strip().lower()
        if a_l == b_l: return True
        if not a_l or not b_l: return False
        # token overlap
        a_t, b_t = set(a_l.split()), set(b_l.split())
        if not a_t or not b_t: return False
        return len(a_t & b_t) / max(len(a_t | b_t), 1) >= threshold
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys(): return False
        return all(_fuzzy_eq(a[k], b[k], threshold=threshold) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b): return False
        return all(_fuzzy_eq(x, y, threshold=threshold) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        # 5% tolerance for numbers
        denom = max(abs(a), abs(b), 1)
        return abs(a - b) / denom < 0.05
    return False


class ConfidenceEstimator:
    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights or DEFAULT_WEIGHTS
        # Normalize weights to sum to 1
        total = sum(self.weights.values()) or 1
        self.weights = {k: v / total for k, v in self.weights.items()}

    def from_signals(self, signals: dict[str, float],
                      weights: dict[str, float] | None = None) -> float:
        """Weighted average of signal scores. Signals not in weights are ignored."""
        w = weights if weights is not None else self.weights
        score = 0.0
        total_w = 0.0
        for k, v in signals.items():
            if k in w:
                score += v * w[k]
                total_w += w[k]
        if total_w == 0:
            return 0.0
        return min(1.0, max(0.0, score / total_w))

    def from_consensus(self, outputs: list[Any],
                        comparator: Callable[[Any, Any], bool] | None = None) -> float:
        """Returns fraction of pairs that match (per fuzzy comparator).
        N=2: 1.0 if match, else 0.0. N=3+: average pairwise."""
        if len(outputs) < 2:
            return 1.0 if outputs else 0.0
        eq = comparator or _fuzzy_eq
        matches = 0
        pairs = 0
        for i in range(len(outputs)):
            for j in range(i + 1, len(outputs)):
                pairs += 1
                if eq(outputs[i], outputs[j]):
                    matches += 1
        return matches / pairs if pairs else 0.0

    def calibrate(self, eval_results: list[dict],
                   confidence_field: str = "confidence",
                   accuracy_field: str = "accuracy",
                   bins: tuple[tuple[float, float], ...] | None = None,
                   ) -> CalibrationReport:
        """
        Bin eval_results by claimed confidence; compute ECE per bin.

        eval_results: list of dicts each with confidence_field + accuracy_field (0-1)
        Returns CalibrationReport. ECE = Σ (bin_size/n) * |avg_conf - actual_acc|.
        """
        if bins is None:
            bins = ((0.0, 0.5), (0.5, 0.7), (0.7, 0.85),
                     (0.85, 0.95), (0.95, 1.001))
        relevant = [r for r in eval_results
                     if confidence_field in r and accuracy_field in r
                     and r[confidence_field] is not None]
        if not relevant:
            return CalibrationReport(ece=0.0, bins=[], n=0, well_calibrated=True)

        bin_stats = []
        ece = 0.0
        n = len(relevant)
        for low, high in bins:
            in_bin = [r for r in relevant
                       if low <= r[confidence_field] < high]
            if not in_bin:
                bin_stats.append(BinStat(low, high, 0, None, None))
                continue
            avg_conf = sum(r[confidence_field] for r in in_bin) / len(in_bin)
            actual = sum(r[accuracy_field] for r in in_bin) / len(in_bin)
            bin_stats.append(BinStat(low, high, len(in_bin), avg_conf, actual))
            ece += (len(in_bin) / n) * abs(avg_conf - actual)

        return CalibrationReport(
            ece=round(ece, 4), bins=bin_stats, n=n,
            well_calibrated=ece < 0.10,
        )

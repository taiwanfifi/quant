"""Eval suite runner."""
from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class EvalCase:
    id: str
    input: dict
    expected: dict | None = None
    invariants: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class EvalResult:
    case_id: str
    output: dict
    scores: dict[str, float]
    cost_usd: float
    latency_ms: int
    confidence: float | None = None
    failure_mode: str | None = None
    trace_id: str = ""
    error: str | None = None


@dataclass
class EvalReport:
    suite_name: str
    run_at: float
    n_cases: int
    n_success: int
    accuracy: float                      # mean of all per-case "primary" score
    avg_cost_usd: float
    avg_latency_ms: int
    total_cost_usd: float
    failure_distribution: dict[str, int]
    score_breakdown: dict[str, float]    # mean of each named score
    calibration: dict[str, Any]          # { "bins": [...], "ece": float }
    results: list[EvalResult]


class EvalKit:
    def __init__(self, *, cost_ledger=None):
        self.cost_ledger = cost_ledger

    def run(
        self,
        suite_path: str | Path,
        runner: Callable[[dict], dict],
        scorers: list,
        *,
        primary_score: str = "accuracy",
        budget_usd: float | None = None,
        on_case: Callable[[EvalResult], None] | None = None,
    ) -> EvalReport:
        suite_path = Path(suite_path)
        cases = [EvalCase(**json.loads(line)) for line in suite_path.read_text().splitlines() if line.strip()]
        results: list[EvalResult] = []
        run_at = time.time()
        cumulative_cost = 0.0

        for case in cases:
            t0 = time.time()
            try:
                out = runner(case.input)
                # Conventions: runner may return {"output": ..., "confidence": ..., "cost_usd": ..., "trace_id": ...}
                if isinstance(out, dict) and "output" in out and "confidence" in out:
                    output = out["output"]
                    confidence = out.get("confidence")
                    cost_usd = float(out.get("cost_usd", 0.0))
                    trace_id = str(out.get("trace_id", ""))
                else:
                    output = out
                    confidence = None
                    cost_usd = 0.0
                    trace_id = ""
                latency_ms = int((time.time() - t0) * 1000)

                scores: dict[str, float] = {}
                for s in scorers:
                    scores.update(s.score(output, case.expected, case.invariants))

                results.append(EvalResult(
                    case_id=case.id, output=output, scores=scores,
                    cost_usd=cost_usd, latency_ms=latency_ms,
                    confidence=confidence, trace_id=trace_id,
                ))
                cumulative_cost += cost_usd

            except Exception as e:
                results.append(EvalResult(
                    case_id=case.id, output={}, scores={},
                    cost_usd=0.0, latency_ms=int((time.time() - t0) * 1000),
                    failure_mode="runner_error", error=str(e),
                ))

            if on_case:
                on_case(results[-1])

            if budget_usd is not None and cumulative_cost >= budget_usd:
                # stop early
                break

        # Aggregate
        n_success = sum(1 for r in results if not r.error and r.scores)
        score_keys = set()
        for r in results:
            score_keys.update(r.scores.keys())
        score_breakdown: dict[str, float] = {}
        for k in score_keys:
            vals = [r.scores[k] for r in results if k in r.scores]
            if vals:
                score_breakdown[k] = sum(vals) / len(vals)

        accuracy = score_breakdown.get(primary_score, 0.0)
        failure_dist: dict[str, int] = defaultdict(int)
        for r in results:
            if r.failure_mode:
                failure_dist[r.failure_mode] += 1

        calibration = _compute_calibration(results, primary_score)

        return EvalReport(
            suite_name=suite_path.stem,
            run_at=run_at,
            n_cases=len(results),
            n_success=n_success,
            accuracy=accuracy,
            avg_cost_usd=sum(r.cost_usd for r in results) / max(1, len(results)),
            avg_latency_ms=int(sum(r.latency_ms for r in results) / max(1, len(results))),
            total_cost_usd=cumulative_cost,
            failure_distribution=dict(failure_dist),
            score_breakdown=score_breakdown,
            calibration=calibration,
            results=results,
        )


def _compute_calibration(results: list[EvalResult], primary_score: str) -> dict:
    """Bin by confidence, compute Expected Calibration Error (ECE)."""
    with_conf = [r for r in results if r.confidence is not None and primary_score in r.scores]
    if not with_conf:
        return {"bins": [], "ece": None, "n_with_confidence": 0}
    bins = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 0.95), (0.95, 1.01)]
    bin_data = []
    ece = 0.0
    total = len(with_conf)
    for low, high in bins:
        in_bin = [r for r in with_conf if low <= r.confidence < high]
        if not in_bin:
            bin_data.append({"range": [low, high], "n": 0, "avg_conf": None, "actual_acc": None})
            continue
        avg_conf = sum(r.confidence for r in in_bin) / len(in_bin)
        actual_acc = sum(r.scores[primary_score] for r in in_bin) / len(in_bin)
        bin_data.append({
            "range": [low, high], "n": len(in_bin),
            "avg_conf": round(avg_conf, 3), "actual_acc": round(actual_acc, 3),
        })
        ece += (len(in_bin) / total) * abs(avg_conf - actual_acc)
    return {"bins": bin_data, "ece": round(ece, 3), "n_with_confidence": total}

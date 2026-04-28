"""Score functions — return dict[str, float] for one (output, expected) pair."""
from __future__ import annotations

from typing import Any, Protocol


class Scorer(Protocol):
    def score(self, output: dict, expected: dict | None,
              invariants: list[str]) -> dict[str, float]: ...


class ExactMatchScorer:
    """Returns 1.0 if `output[field] == expected[field]` for each field; else 0.0.
    Each field becomes a separate score key named `match_<field>`."""

    def __init__(self, fields: list[str], primary: str = "accuracy"):
        self.fields = fields
        self.primary = primary

    def score(self, output, expected, invariants) -> dict[str, float]:
        if expected is None:
            return {}
        scores = {}
        per_field = []
        for f in self.fields:
            ok = 1.0 if output.get(f) == expected.get(f) else 0.0
            scores[f"match_{f}"] = ok
            per_field.append(ok)
        scores[self.primary] = sum(per_field) / max(1, len(per_field))
        return scores


class StructuralScorer:
    """Validates output has required keys + correct types. Doesn't compare values."""

    def __init__(self, schema: dict[str, type]):
        self.schema = schema

    def score(self, output, expected, invariants) -> dict[str, float]:
        ok = 1.0
        for key, expected_type in self.schema.items():
            if key not in output:
                ok = 0.0
                break
            if not isinstance(output[key], expected_type):
                ok = 0.0
                break
        return {"schema_valid": ok}


class InvariantScorer:
    """Runs named invariant checks. Each returns 0/1.
    Caller registers invariants via `register(name, fn)` where fn(output) -> bool.
    """

    def __init__(self):
        self._fns: dict[str, Any] = {}

    def register(self, name: str, fn):
        self._fns[name] = fn

    def score(self, output, expected, invariants) -> dict[str, float]:
        scores = {}
        for inv in invariants:
            fn = self._fns.get(inv)
            if fn is None:
                scores[f"inv_{inv}"] = 0.0  # unknown invariant counts as fail
                continue
            try:
                scores[f"inv_{inv}"] = 1.0 if fn(output) else 0.0
            except Exception:
                scores[f"inv_{inv}"] = 0.0
        return scores

"""Evaluation result structures and summary calculation."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class CaseResult:
    case_id: str
    passed: bool
    expected_intent: str | None = None
    actual_intent: str | None = None
    expected_tool: str | None = None
    actual_tool: str | None = None
    expected_arguments: dict[str, Any] = field(default_factory=dict)
    actual_arguments: dict[str, Any] = field(default_factory=dict)
    latency_ms: float | None = None
    detail: str = ""


@dataclass(frozen=True, slots=True)
class EvaluationSummary:
    total: int
    passed: int
    failed: int
    pass_rate: float


def summarize(results: list[CaseResult]) -> EvaluationSummary:
    passed = sum(result.passed for result in results)
    total = len(results)
    return EvaluationSummary(
        total=total,
        passed=passed,
        failed=total - passed,
        pass_rate=(passed / total * 100) if total else 0.0,
    )

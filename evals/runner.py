"""Credentials-free Croatian deterministic evaluation runner."""

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agent.intents import (
    classify_confirmation,
    classify_intent,
    classify_medication_response,
    extract_integer,
    extract_safety_subtype,
)
from app.domain.medication_rules import assert_not_medical_advice
from app.domain.time_parser import parse_appointment_offset, parse_croatian_time
from app.utils.phone_numbers import normalize_phone_number
from app.utils.redaction import redact_phone
from evals.metrics import CaseResult, summarize

TOOLS = {
    "general_reminder_create": "schedule_reminder",
    "safety_reminder_create": "schedule_reminder",
    "medication_plan_create": "create_medication_plan",
    "medication_response": "record_medication_response",
    "medication_inventory_query": "get_medication_inventory",
    "medication_inventory_add": "add_medication_inventory",
    "medication_inventory_set": "set_medication_inventory",
    "appointment_create": "create_doctor_appointment",
    "appointment_query": "get_next_doctor_appointment",
    "appointment_update": "update_doctor_appointment",
    "appointment_cancel": "cancel_doctor_appointment",
    "reminder_list": "list_upcoming_reminders",
    "reminder_cancel": "cancel_reminder",
    "unknown": None,
}
FIXED_NOW = datetime(2026, 8, 4, 6, 0, tzinfo=UTC)


def load_cases(directory: Path | None = None) -> list[dict[str, Any]]:
    root = directory or Path(__file__).parent / "datasets"
    cases: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                cases.append(json.loads(line))
    return cases


def evaluate_case(case: dict[str, Any]) -> CaseResult:
    started = time.perf_counter()
    kind = case["kind"]
    expected = case.get("expected")
    actual: Any = None
    expected_intent = None
    actual_intent = None
    expected_tool = None
    actual_tool = None
    expected_arguments = case.get("expected_arguments", {})
    actual_arguments: dict[str, Any] = {}
    try:
        if kind == "intent":
            actual_intent = classify_intent(case["utterance"]).value
            expected_intent = str(expected)
            expected_tool = case.get("expected_tool", TOOLS.get(expected_intent))
            actual_tool = TOOLS.get(actual_intent) if actual_intent is not None else None
            if "subtype" in expected_arguments:
                actual_arguments["subtype"] = extract_safety_subtype(case["utterance"])
            if "integer" in expected_arguments:
                actual_arguments["integer"] = extract_integer(case["utterance"])
            actual = (actual_intent, actual_tool, actual_arguments)
            expected = (expected_intent, expected_tool, expected_arguments)
        elif kind == "time":
            parsed = parse_croatian_time(case["utterance"], now=FIXED_NOW)
            if "offset_minutes" in expected_arguments:
                actual_arguments["offset_minutes"] = round((parsed.scheduled_for - FIXED_NOW).total_seconds() / 60)
            if "local_time" in expected_arguments:
                actual_arguments["local_time"] = parsed.local_time.strftime("%H:%M") if parsed.local_time else None
            if "recurrence_prefix" in expected_arguments:
                actual_arguments["recurrence_prefix"] = (
                    parsed.recurrence_rule.split(";")[0] if parsed.recurrence_rule else None
                )
            actual = actual_arguments
            expected = expected_arguments
        elif kind == "appointment_offset":
            minutes, clock = parse_appointment_offset(case["utterance"])
            actual = {"minutes": minutes, "clock": clock.strftime("%H:%M") if clock else None}
        elif kind == "confirmation":
            actual = classify_confirmation(case["utterance"])
        elif kind == "medication_response":
            actual = classify_medication_response(case["utterance"]).value
        elif kind == "phone":
            actual = normalize_phone_number(case["utterance"])
        elif kind == "medical_safety":
            actual = assert_not_medical_advice(case["utterance"])
        elif kind == "redaction":
            actual = redact_phone(case["utterance"])
        else:
            raise ValueError(f"Unknown eval kind: {kind}")
        passed = actual == expected
        detail = "" if passed else f"expected={expected!r}, actual={actual!r}"
    except Exception as exc:
        passed = False
        detail = f"{type(exc).__name__}: {exc}"
    return CaseResult(
        case_id=case["id"],
        passed=passed,
        expected_intent=expected_intent,
        actual_intent=actual_intent,
        expected_tool=expected_tool,
        actual_tool=actual_tool,
        expected_arguments=expected_arguments,
        actual_arguments=actual_arguments,
        latency_ms=(time.perf_counter() - started) * 1000,
        detail=detail,
    )


def run() -> list[CaseResult]:
    return [evaluate_case(case) for case in load_cases()]


def main() -> None:
    results = run()
    summary = summarize(results)
    print(f"total={summary.total} passed={summary.passed} failed={summary.failed} pass_rate={summary.pass_rate:.1f}%")
    for result in results:
        if not result.passed:
            print(
                f"FAIL {result.case_id}: expected_intent={result.expected_intent} "
                f"actual_intent={result.actual_intent} expected_tool={result.expected_tool} "
                f"actual_tool={result.actual_tool} expected_arguments={result.expected_arguments} "
                f"actual_arguments={result.actual_arguments} latency_ms={result.latency_ms:.2f} "
                f"detail={result.detail}"
            )
    raise SystemExit(0 if summary.failed == 0 else 1)


if __name__ == "__main__":
    main()

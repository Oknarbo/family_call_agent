"""Outbound LangGraph policy tests."""

import pytest

from app.agent.appointment_graph import build_appointment_outbound_graph
from app.agent.medication_graph import build_medication_outbound_graph
from app.agent.safety_graph import build_safety_outbound_graph
from app.config import Settings
from app.domain.enums import SafetyReminderOutcome
from app.repositories.memory import MemoryStore
from app.services.household_safety import HouseholdSafetyService


@pytest.mark.parametrize(
    ("text", "outcome", "action"),
    [
        ("Nisam ugasila plin", "not_completed", "clarify"),
        ("Ne znam jesam li ugasila plin", "unclear", "clarify"),
        ("Nisam sigurna jesam li maknula čaj", "unclear", "clarify"),
        ("Mislim da jesam", "unclear", "clarify"),
        ("Možda sam ugasila plin", "unclear", "clarify"),
        ("Jesam, ali nisam ugasila plin", "not_completed", "clarify"),
        ("Ugasila bih plin", "unclear", "clarify"),
        ("Čaj je skoro gotov", "unclear", "clarify"),
        ("Nazovi me za dvije minute", "call_again_requested", "retry"),
        ("Nemoj me nazovi", "not_completed", "clarify"),
        ("Ugasila sam plin.", "completed", "complete"),
        ("Da, ugasio sam plin!", "completed", "complete"),
        ("Maknula sam čajnik", "completed", "complete"),
        ("Jesam!", "completed", "complete"),
        ("  ", "no_answer", "retry"),
    ],
)
def test_safety_confirmation_and_service_policy(
    text: str, outcome: str, action: str, store: MemoryStore, settings: Settings
) -> None:
    result = build_safety_outbound_graph().invoke({"response_text": text, "attempt_number": 1})
    assert result["outcome"] == outcome
    assert result["action"] == action
    assert HouseholdSafetyService(store, settings).next_action(SafetyReminderOutcome(outcome), 1) == action


def test_medication_graph_only_flags_confirmed_inventory_adjustment() -> None:
    graph = build_medication_outbound_graph()
    assert graph.invoke({"response_text": "Popila sam"})["inventory_adjusted"] is True
    assert graph.invoke({"response_text": "Ne sjećam se"})["inventory_adjusted"] is False


def test_safety_graph_escalates_repeated_no_answer() -> None:
    graph = build_safety_outbound_graph()
    result = graph.invoke({"response_text": "", "attempt_number": 2, "escalate_after": 2})
    assert result["outcome"] == "no_answer"
    assert result["action"] == "escalate"


def test_appointment_attendance_is_not_an_outbound_inference() -> None:
    result = build_appointment_outbound_graph().invoke({"response_text": "Jesam, zapamtila sam"})
    assert result["outcome"] == "remembered"
    assert "completed" not in result["outcome"]

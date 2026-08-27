"""Main LangGraph conditional routing and multi-turn tests."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.agent.graph import build_inbound_graph
from app.config import Settings
from app.repositories.memory import MemoryStore
from app.schemas import FamilyMemberRecord


def _state(
    member: FamilyMemberRecord,
    utterance: str,
    *,
    pending_action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "call_id": f"test-{uuid4()}",
        "caller_user_id": str(member.id),
        "caller_phone": member.phone_number_e164,
        "caller_is_registered": True,
        "caller_name": member.display_name,
        "caller_role": member.role.value,
        "transcript": [],
        "current_utterance": utterance,
        "pending_action": pending_action,
        "clarification_count": 0,
        "now_iso": datetime.now(UTC).isoformat(),
    }


def test_state_change_waits_for_confirmation(store: MemoryStore, mama: FamilyMemberRecord, settings: Settings) -> None:
    graph = build_inbound_graph(store, settings)
    state = graph.invoke(_state(mama, "Stavila sam čaj, nazovi me za pet minuta."))
    assert state["confirmation_status"] == "awaiting"
    assert store.reminders == {}
    state["current_utterance"] = "Da"
    completed = graph.invoke(state)
    assert completed["response_text"] == "Dogovoreno."
    assert len(store.reminders) == 1


def test_rejection_cancels_pending_action(store: MemoryStore, mama: FamilyMemberRecord, settings: Settings) -> None:
    graph = build_inbound_graph(store, settings)
    state = graph.invoke(_state(mama, "Podsjeti me za deset minuta da ugasim pećnicu."))
    state["current_utterance"] = "Ne"
    completed = graph.invoke(state)
    assert completed["pending_action"] is None
    assert store.reminders == {}


def test_correction_rebuilds_confirmation(store: MemoryStore, mama: FamilyMemberRecord, settings: Settings) -> None:
    graph = build_inbound_graph(store, settings)
    state = graph.invoke(_state(mama, "Stavila sam čaj, nazovi me za pet minuta."))
    first_time = state["pending_action"]["arguments"]["scheduled_for"]
    state["current_utterance"] = "Nije za pet nego za deset minuta"
    corrected = graph.invoke(state)
    second_time = corrected["pending_action"]["arguments"]["scheduled_for"]
    assert second_time > first_time
    assert corrected["confirmation_status"] == "awaiting"


def test_medication_plan_asks_one_question_then_confirms(
    store: MemoryStore, mama: FamilyMemberRecord, settings: Settings
) -> None:
    graph = build_inbound_graph(store, settings)
    state = graph.invoke(_state(mama, "Nazovi me svaki dan u 12 da popijem tabletu. Imam ih 30."))
    assert state["response_text"] == "Kako se zove tableta?"
    state["current_utterance"] = "Normabel"
    state = graph.invoke(state)
    assert state["confirmation_status"] == "awaiting"
    assert store.medication_plans == {}
    state["current_utterance"] = "Može"
    completed = graph.invoke(state)
    assert completed["response_text"] == "Dogovoreno."
    assert next(iter(store.medication_plans.values())).current_inventory == 30


def test_medication_plan_for_another_family_member_uses_target_in_confirmation(
    store: MemoryStore, branko: FamilyMemberRecord, mama: FamilyMemberRecord, settings: Settings
) -> None:
    graph = build_inbound_graph(store, settings)
    state = graph.invoke(_state(branko, "Podsjeti mamu svaki dan u 12 da popije tabletu."))
    assert state["response_text"] == "Kako se zove tableta?"
    state["current_utterance"] = "neoforte"
    state = graph.invoke(state)
    assert "mamu" in state["response_text"].casefold()
    assert "zvat ću mamu" in state["response_text"].casefold()
    assert state["pending_action"]["arguments"]["target_user_id"] == mama.id
    state["current_utterance"] = "Da"
    completed = graph.invoke(state)
    assert completed["response_text"] == "Dogovoreno."
    plan = next(iter(store.medication_plans.values()))
    assert plan.user_id == mama.id


def test_unknown_caller_is_rejected_without_leaking_family(store: MemoryStore, settings: Settings) -> None:
    graph = build_inbound_graph(store, settings)
    state = {
        "call_id": "unknown",
        "caller_phone": "+385991234567",
        "caller_is_registered": False,
        "current_utterance": "Kad mama ima doktora?",
        "now_iso": datetime.now(UTC).isoformat(),
    }
    result = graph.invoke(state)
    assert "nije registriran" in result["response_text"]
    assert "Mama" not in result["response_text"]

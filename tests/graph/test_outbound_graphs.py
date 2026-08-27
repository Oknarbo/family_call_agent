"""Outbound LangGraph policy tests."""

from app.agent.appointment_graph import build_appointment_outbound_graph
from app.agent.medication_graph import build_medication_outbound_graph
from app.agent.safety_graph import build_safety_outbound_graph


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

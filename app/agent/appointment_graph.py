"""Provider-neutral doctor appointment reminder graph."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class AppointmentOutboundState(TypedDict, total=False):
    appointment_id: str
    response_text: str
    outcome: str
    followup_requested: bool


def _classify(text: str) -> str:
    value = text.casefold()
    if "ponovi" in value:
        return "repeat_requested"
    if "javi" in value:
        return "family_notification_requested"
    if "nazovi" in value or "podsjeti" in value:
        return "followup_requested"
    if any(word in value for word in ("jesam", "zapamtila", "u redu")):
        return "remembered"
    return "unclear"


def build_appointment_outbound_graph() -> object:
    graph = StateGraph(AppointmentOutboundState)
    graph.add_node("load_appointment", lambda _state: {})
    graph.add_node("classify_response", lambda state: {"outcome": _classify(state.get("response_text", ""))})
    graph.add_node(
        "save_outcome",
        lambda state: {"followup_requested": state.get("outcome") == "followup_requested"},
    )
    graph.add_edge(START, "load_appointment")
    graph.add_edge("load_appointment", "classify_response")
    graph.add_edge("classify_response", "save_outcome")
    graph.add_edge("save_outcome", END)
    return graph.compile()

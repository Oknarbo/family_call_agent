"""Outbound medication reminder graph skeleton with deterministic outcome routing."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.agent.intents import classify_medication_response


class MedicationOutboundState(TypedDict, total=False):
    medication_plan_id: str
    dose_event_id: str
    response_text: str
    outcome: str
    inventory_adjusted: bool
    next_action: str


def build_medication_outbound_graph() -> object:
    """Compile provider-neutral medication outcome processing."""

    graph = StateGraph(MedicationOutboundState)
    graph.add_node(
        "load_scheduled_dose",
        lambda state: {"inventory_adjusted": False, "next_action": "collect_response"},
    )
    graph.add_node(
        "classify_response",
        lambda state: {"outcome": classify_medication_response(state.get("response_text", "")).value},
    )
    graph.add_node(
        "apply_rules",
        lambda state: {
            "inventory_adjusted": state.get("outcome") == "user_reported_taken",
            "next_action": ("call_later" if state.get("outcome") == "call_later_requested" else "persist"),
        },
    )
    graph.add_edge(START, "load_scheduled_dose")
    graph.add_edge("load_scheduled_dose", "classify_response")
    graph.add_edge("classify_response", "apply_rules")
    graph.add_edge("apply_rules", END)
    return graph.compile()

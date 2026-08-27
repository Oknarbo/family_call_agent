"""Household safety reminder outcome graph."""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph


class SafetyOutboundState(TypedDict, total=False):
    reminder_id: str
    response_text: str
    attempt_number: int
    outcome: str
    action: str
    escalate_after: int


def _classify(text: str) -> str:
    value = text.casefold()
    if any(word in value for word in ("jesam", "ugasila", "maknula", "gotov")):
        return "completed"
    if "nazovi" in value or "zovni" in value:
        return "call_again_requested"
    if any(word in value for word in ("nisam", "još nije")):
        return "not_completed"
    if not value.strip():
        return "no_answer"
    return "unclear"


def build_safety_outbound_graph() -> object:
    graph = StateGraph(SafetyOutboundState)
    graph.add_node("load_safety_reminder", lambda _state: {})
    graph.add_node("classify_response", lambda state: {"outcome": _classify(state.get("response_text", ""))})

    def policy(state: SafetyOutboundState) -> dict[str, str]:
        outcome = state.get("outcome")
        attempts = state.get("attempt_number", 1)
        threshold = state.get("escalate_after", 2)
        if outcome == "call_again_requested":
            return {"action": "retry"}
        if outcome == "no_answer" and attempts >= threshold:
            return {"action": "escalate"}
        if outcome == "no_answer":
            return {"action": "retry"}
        return {"action": "complete"}

    graph.add_node("apply_retry_policy", policy)
    graph.add_edge(START, "load_safety_reminder")
    graph.add_edge("load_safety_reminder", "classify_response")
    graph.add_edge("classify_response", "apply_retry_policy")
    graph.add_edge("apply_retry_policy", END)
    return graph.compile()

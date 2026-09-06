"""Household safety reminder outcome graph."""

import re
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
    value = " ".join(text.casefold().split()).strip(" .!?,")
    if not value:
        return "no_answer"
    # Doubt and negation take precedence over words such as "jesam" or "ugasila".
    if re.search(r"\b(ne znam|ne sjećam se|nisam siguran|nisam sigurna|možda|valjda|mislim|jesam li)\b", value):
        return "unclear"
    if re.search(r"\b(nazovi|zovni|podsjeti)\b", value) and not re.search(r"\b(ne|nemoj)\b", value):
        return "call_again_requested"
    if re.search(r"\b(ne|nisam|nismo|nije|nisu|nemoj)\b", value):
        return "not_completed"
    # Only explicit, bounded confirmations complete a reminder. Extra clauses
    # require clarification instead of being accepted by substring matching.
    if re.fullmatch(
        r"(?:(?:da|jesam)[, ]+)?(?:"
        r"jesam|da|gotovo|gotov je čaj|"
        r"(?:ugasila|ugasio|maknula|maknuo|isključila|isključio) sam"
        r"(?: (?:plin|štednjak|pećnicu|čaj|čajnik|lonac|glačalo))?"
        r")",
        value,
    ):
        return "completed"
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
        if outcome == "completed":
            return {"action": "complete"}
        return {"action": "clarify"}

    graph.add_node("apply_retry_policy", policy)
    graph.add_edge(START, "load_safety_reminder")
    graph.add_edge("load_safety_reminder", "classify_response")
    graph.add_edge("classify_response", "apply_retry_policy")
    graph.add_edge("apply_retry_policy", END)
    return graph.compile()

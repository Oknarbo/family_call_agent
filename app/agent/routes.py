"""Conditional-edge routing kept explicit for graph tests."""

from app.agent.state import ConversationState
from app.domain.enums import READ_ONLY_INTENTS, Intent


def route_after_identity(state: ConversationState) -> str:
    if not state.get("caller_is_registered", False):
        return "reject"
    pending = state.get("pending_action")
    if pending and pending.get("stage") == "awaiting_confirmation":
        return "confirmation"
    if pending and pending.get("stage") == "clarifying":
        return "clarification"
    return "new_request"


def route_request(state: ConversationState) -> str:
    if state.get("clarification_question"):
        return "clarify"
    intent = Intent(state.get("intent") or Intent.UNKNOWN)
    if intent == Intent.UNKNOWN:
        return "unsupported"
    if intent in READ_ONLY_INTENTS:
        return "read"
    return "write"


def route_confirmation(state: ConversationState) -> str:
    status = state.get("confirmation_status")
    if status == "confirmed":
        return "execute"
    if status == "rejected":
        return "cancel"
    if status == "correction_requested":
        return "correction"
    return "unclear"

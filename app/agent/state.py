"""Typed state shared by voice and text transports."""

from typing import Any, Literal, TypedDict


class ConversationState(TypedDict, total=False):
    call_id: str
    provider_call_id: str | None
    caller_phone: str
    caller_user_id: str | None
    caller_name: str | None
    caller_role: str | None
    caller_is_registered: bool
    transcript: list[dict[str, Any]]
    current_utterance: str
    intent: str | None
    extracted_arguments: dict[str, Any]
    resolved_references: dict[str, Any]
    pending_action: dict[str, Any] | None
    action_requires_confirmation: bool
    confirmation_status: Literal["not_required", "awaiting", "confirmed", "rejected", "correction_requested"] | None
    clarification_question: str | None
    clarification_count: int
    tool_name: str | None
    tool_arguments: dict[str, Any] | None
    tool_result: dict[str, Any] | None
    response_text: str | None
    error_code: str | None
    error_message: str | None
    now_iso: str

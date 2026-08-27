"""Main inbound LangGraph used by every conversation transport."""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agent.nodes import InboundNodes
from app.agent.routes import route_after_identity, route_confirmation, route_request
from app.agent.state import ConversationState
from app.config import Settings
from app.repositories.protocols import Store


def build_inbound_graph(
    store: Store, settings: Settings
) -> CompiledStateGraph[ConversationState, None, ConversationState, ConversationState]:
    """Compile the confirmation-gated inbound conversation graph."""

    nodes = InboundNodes(store, settings)
    graph: StateGraph[ConversationState, None, ConversationState, ConversationState] = StateGraph(ConversationState)
    graph.add_node("load_call_context", nodes.load_call_context)
    # LangGraph 1.2 infers Never for nodes whose state parameter is intentionally unused.
    graph.add_node("reject_unknown_caller", nodes.reject_unknown_caller)  # type: ignore[arg-type]
    graph.add_node("classify_intent", nodes.classify_request)
    graph.add_node("extract_arguments", nodes.extract_arguments)
    graph.add_node("validate_request", nodes.validate_request)
    graph.add_node("ask_one_clarification", nodes.ask_one_clarification)
    graph.add_node("apply_clarification", nodes.apply_clarification)
    graph.add_node("build_confirmation", nodes.build_confirmation)
    graph.add_node("classify_confirmation", nodes.classify_confirmation_node)
    graph.add_node("execute_write_tool", nodes.execute_write_tool)
    graph.add_node("execute_read_tool", nodes.execute_read_tool)
    graph.add_node("cancel_pending_action", nodes.cancel_pending_action)  # type: ignore[arg-type]
    graph.add_node("ask_confirmation_again", nodes.ask_confirmation_again)
    graph.add_node("apply_correction", nodes.apply_correction)
    graph.add_node("unsupported", nodes.unsupported)  # type: ignore[arg-type]

    graph.add_edge(START, "load_call_context")
    graph.add_conditional_edges(
        "load_call_context",
        route_after_identity,
        {
            "reject": "reject_unknown_caller",
            "confirmation": "classify_confirmation",
            "clarification": "apply_clarification",
            "new_request": "classify_intent",
        },
    )
    graph.add_edge("reject_unknown_caller", END)
    graph.add_edge("classify_intent", "extract_arguments")
    graph.add_edge("extract_arguments", "validate_request")
    graph.add_conditional_edges(
        "validate_request",
        route_request,
        {
            "clarify": "ask_one_clarification",
            "read": "execute_read_tool",
            "write": "build_confirmation",
            "unsupported": "unsupported",
        },
    )
    graph.add_edge("ask_one_clarification", END)
    graph.add_edge("execute_read_tool", END)
    graph.add_edge("build_confirmation", END)
    graph.add_edge("unsupported", END)
    graph.add_conditional_edges(
        "classify_confirmation",
        route_confirmation,
        {
            "execute": "execute_write_tool",
            "cancel": "cancel_pending_action",
            "correction": "apply_correction",
            "unclear": "ask_confirmation_again",
        },
    )
    graph.add_edge("execute_write_tool", END)
    graph.add_edge("cancel_pending_action", END)
    graph.add_edge("ask_confirmation_again", END)
    graph.add_conditional_edges(
        "apply_correction",
        lambda state: "clarify" if state.get("clarification_question") else "confirm",
        {"clarify": END, "confirm": "build_confirmation"},
    )
    graph.add_conditional_edges(
        "apply_clarification",
        lambda state: "clarify" if state.get("clarification_question") else "confirm",
        {"clarify": END, "confirm": "build_confirmation"},
    )
    return graph.compile()

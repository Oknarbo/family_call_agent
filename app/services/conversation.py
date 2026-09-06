"""One conversation turn against the same durable store used by workers."""

from typing import cast

from app.agent.graph import build_inbound_graph
from app.agent.state import ConversationState
from app.config import Settings, get_settings
from app.dependencies import application_store


async def conversation_turn(state: ConversationState, settings: Settings | None = None) -> ConversationState:
    active = settings or get_settings()
    async with application_store(active) as store:
        result = await build_inbound_graph(store, active).ainvoke(state)
        # Graph nodes report domain errors as state instead of raising. Discard
        # all staged writes even if a service mutated records before the error.
        if result.get("error_code"):
            store.abort()
        return cast(ConversationState, result)

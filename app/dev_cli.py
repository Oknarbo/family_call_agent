"""Text simulator using the exact inbound LangGraph used by voice transports."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from app.agent.graph import build_inbound_graph
from app.agent.prompts import INTRODUCTION
from app.agent.state import ConversationState
from app.config import get_settings
from app.repositories.memory import MemoryStore
from app.services.family_directory import FamilyDirectory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Zvonko lokalni tekstualni simulator")
    parser.add_argument(
        "--caller",
        default=None,
        choices=["mama", "tata", "branko", "nataša", "unknown"],
        help="Tko zove Zvonka (obavezno za razgovor)",
    )
    parser.add_argument("--data", type=Path, default=Path("zvonko-dev.json"))
    parser.add_argument("--reset", action="store_true", help="Obriši lokalne razvojne podatke")
    parser.add_argument("--show-state", action="store_true", help="Prikaži spremljeno strukturirano stanje")
    parser.add_argument("--simulate-due", action="store_true", help="Prikaži dospjele zakazane događaje")
    return parser


def _show_state(store: MemoryStore) -> None:
    data = {
        "reminders": [record.model_dump(mode="json") for record in store.reminders.values()],
        "medication_plans": [record.model_dump(mode="json") for record in store.medication_plans.values()],
        "appointments": [record.model_dump(mode="json") for record in store.appointments.values()],
    }
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _simulate_due(store: MemoryStore) -> None:
    now = datetime.now(UTC)
    due = [item for item in store.reminders.values() if item.scheduled_for <= now]
    if not due:
        print("Nema dospjelih događaja.")
        return
    for item in due:
        print(f"Zvonko (simulirani poziv): {item.message}")


def main() -> None:
    args = build_parser().parse_args()
    settings = get_settings()
    store = MemoryStore(args.data)
    directory = FamilyDirectory(store)
    if args.reset:
        store.reset()
        directory.seed(settings)
        print("Razvojni podaci obrisani; obitelj učitana iz .env.")
    elif not store.family_members:
        directory.seed(settings)
    if args.show_state:
        _show_state(store)
        return
    if args.simulate_due:
        _simulate_due(store)
        return
    if args.caller is None:
        if args.reset:
            return
        build_parser().error("Odaberi tko zove: --caller mama|tata|branko|nataša|unknown")
    caller = None if args.caller == "unknown" else directory.by_name(args.caller)
    state: ConversationState = {
        "call_id": f"cli-{uuid4()}",
        "caller_user_id": str(caller.id) if caller else None,
        "caller_phone": "+385991234567" if caller is None else caller.phone_number_e164,
        "caller_is_registered": caller is not None,
        "transcript": [],
        "pending_action": None,
        "clarification_count": 0,
        "now_iso": datetime.now(UTC).isoformat(),
    }
    graph = build_inbound_graph(store, settings)
    print(f"Zvonko: {INTRODUCTION}")
    while True:
        try:
            utterance = input(f"{caller.display_name if caller else 'Pozivatelj'}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nZvonko: Doviđenja.")
            break
        if utterance.casefold() in {"izlaz", "kraj", "doviđenja"}:
            print("Zvonko: Doviđenja.")
            break
        state["current_utterance"] = utterance
        state["now_iso"] = datetime.now(UTC).isoformat()
        state = cast(ConversationState, graph.invoke(state))
        transcript = state.setdefault("transcript", [])
        transcript.extend(
            [
                {"role": "user", "text": utterance},
                {"role": "assistant", "text": state.get("response_text")},
            ]
        )
        print(f"Zvonko: {state.get('response_text')}")
        store.save()


if __name__ == "__main__":
    main()

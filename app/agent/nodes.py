"""Small testable nodes for the main inbound LangGraph."""

import re
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from app.agent.intents import (
    classify_confirmation,
    classify_intent,
    extract_provider_name,
    extract_safety_subtype,
    normalize_utterance,
)
from app.agent.prompts import UNKNOWN_CALLER, format_local, medication_confirmation, target_call_phrase
from app.agent.schemas import (
    AppointmentQueryInput,
    CreateAppointmentInput,
    CreateMedicationPlanInput,
    ListRemindersInput,
    ScheduleReminderInput,
)
from app.agent.state import ConversationState
from app.agent.tools import ToolRegistry
from app.config import Settings
from app.domain.enums import Intent, ReminderType
from app.domain.exceptions import DomainError, ValidationError
from app.domain.time_parser import parse_croatian_time
from app.repositories.protocols import Store
from app.services.family_directory import FamilyDirectory
from app.utils.ids import idempotency_key


class InboundNodes:
    """Node collection with injected repositories and settings."""

    def __init__(self, store: Store, settings: Settings) -> None:
        self.store = store
        self.settings = settings
        self.directory = FamilyDirectory(store)
        self.tools = ToolRegistry(store)

    def load_call_context(self, state: ConversationState) -> dict[str, Any]:
        try:
            if state.get("caller_user_id"):
                member = self.directory.by_id(UUID(str(state["caller_user_id"])))
            else:
                member = self.directory.identify(state.get("caller_phone", ""))
            return {
                "caller_user_id": str(member.id),
                "caller_name": member.display_name,
                "caller_role": member.role.value,
                "caller_is_registered": True,
                "error_code": None,
            }
        except DomainError as exc:
            return {
                "caller_user_id": None,
                "caller_name": None,
                "caller_role": None,
                "caller_is_registered": False,
                "error_code": exc.code,
            }

    def reject_unknown_caller(self, _state: ConversationState) -> dict[str, Any]:
        return {"response_text": UNKNOWN_CALLER, "pending_action": None}

    def classify_request(self, state: ConversationState) -> dict[str, Any]:
        intent = classify_intent(state.get("current_utterance", ""))
        return {"intent": intent.value, "clarification_question": None, "tool_result": None}

    def extract_arguments(self, state: ConversationState) -> dict[str, Any]:
        intent = Intent(state.get("intent") or Intent.UNKNOWN)
        utterance = state.get("current_utterance", "")
        now = datetime.fromisoformat(state["now_iso"]) if state.get("now_iso") else datetime.now(UTC)
        caller_id = UUID(str(state["caller_user_id"]))
        target_id = self._resolve_target(utterance, caller_id)
        arguments: dict[str, Any] = {"requester_user_id": caller_id, "target_user_id": target_id}
        clarification: str | None = None

        if intent in {
            Intent.GENERAL_REMINDER_CREATE,
            Intent.SAFETY_REMINDER_CREATE,
            Intent.MEDICATION_PLAN_CREATE,
            Intent.APPOINTMENT_CREATE,
        }:
            try:
                parsed = parse_croatian_time(utterance, now=now, timezone=self.settings.default_timezone)
                arguments.update(
                    scheduled_for=parsed.scheduled_for,
                    recurrence_rule=parsed.recurrence_rule,
                    local_time=parsed.local_time,
                )
            except ValidationError:
                clarification = "U koliko sati želiš da te nazovem?"

        if intent == Intent.SAFETY_REMINDER_CREATE:
            subtype = extract_safety_subtype(utterance)
            arguments.update(subtype=subtype, message=self._reminder_message(utterance, subtype))
        elif intent == Intent.GENERAL_REMINDER_CREATE:
            arguments["message"] = self._reminder_message(utterance, "general")
        elif intent == Intent.MEDICATION_PLAN_CREATE:
            inventory_match = re.search(r"(?:imam(?: ih)?|ima ih)\s+(\d+)", utterance.casefold())
            arguments["initial_inventory"] = int(inventory_match.group(1)) if inventory_match else None
            name_match = re.search(r"(?:tabletu|lijek)\s+([A-Za-zČĆĐŠŽčćđšž][\wČĆĐŠŽčćđšž-]+)", utterance)
            if name_match and name_match.group(1).casefold() not in {"u", "svaki", "svaku"}:
                arguments["medication_name"] = name_match.group(1)
            else:
                clarification = "Kako se zove tableta?"
        elif intent == Intent.APPOINTMENT_CREATE:
            arguments["provider_name"] = extract_provider_name(utterance)
            if not arguments["provider_name"]:
                clarification = "Kod kojeg doktora ideš?"
        elif intent in {Intent.REMINDER_LIST, Intent.APPOINTMENT_QUERY}:
            arguments["target_user_id"] = target_id
        return {
            "extracted_arguments": arguments,
            "resolved_references": {"target_user_id": str(target_id)},
            "clarification_question": clarification,
        }

    def validate_request(self, state: ConversationState) -> dict[str, Any]:
        question = state.get("clarification_question")
        if question:
            pending = {
                "stage": "clarifying",
                "intent": state.get("intent"),
                "arguments": state.get("extracted_arguments", {}),
                "missing": self._missing_field(question),
            }
            return {"pending_action": pending, "action_requires_confirmation": True}
        return {}

    def ask_one_clarification(self, state: ConversationState) -> dict[str, Any]:
        return {
            "response_text": state.get("clarification_question"),
            "clarification_count": state.get("clarification_count", 0) + 1,
        }

    def apply_clarification(self, state: ConversationState) -> dict[str, Any]:
        pending = dict(state.get("pending_action") or {})
        arguments = dict(pending.get("arguments") or {})
        utterance = state.get("current_utterance", "")
        missing = pending.get("missing")
        question: str | None = None
        if missing == "medication_name":
            normalized = normalize_utterance(utterance)
            arguments["medication_name"] = self._parse_medication_name(utterance, normalized)
        elif missing == "provider_name":
            name = extract_provider_name(utterance) or re.sub(
                r"^kod\s+(?:doktorice|doktora)?\s*", "", utterance, flags=re.IGNORECASE
            ).strip(" .")
            if not name:
                question = "Kako se zove doktor ili doktorica?"
            else:
                arguments["provider_name"] = name
        elif missing == "scheduled_for":
            now = datetime.fromisoformat(state["now_iso"])
            try:
                parsed = parse_croatian_time(utterance, now=now, timezone=self.settings.default_timezone)
                arguments.update(
                    scheduled_for=parsed.scheduled_for,
                    recurrence_rule=parsed.recurrence_rule,
                    local_time=parsed.local_time,
                )
            except ValidationError:
                question = "Nisam dobro razumio vrijeme. U koliko sati želiš da te nazovem?"
        pending["arguments"] = arguments
        if question:
            pending["stage"] = "clarifying"
            return {"pending_action": pending, "clarification_question": question, "response_text": question}
        pending["stage"] = "ready_for_confirmation"
        return {
            "pending_action": pending,
            "extracted_arguments": arguments,
            "intent": pending.get("intent"),
            "clarification_question": None,
        }

    def build_confirmation(self, state: ConversationState) -> dict[str, Any]:
        pending = dict(state.get("pending_action") or {})
        if not pending or pending.get("stage") == "ready_for_confirmation":
            pending = {
                "intent": state.get("intent"),
                "arguments": state.get("extracted_arguments", {}),
            }
        intent = Intent(str(pending["intent"]))
        args = pending["arguments"]
        caller_id = UUID(str(state["caller_user_id"]))
        text = self._confirmation_text(intent, args, caller_id)
        pending.update(stage="awaiting_confirmation", confirmation_text=text)
        return {
            "pending_action": pending,
            "action_requires_confirmation": True,
            "confirmation_status": "awaiting",
            "response_text": text,
        }

    def classify_confirmation_node(self, state: ConversationState) -> dict[str, Any]:
        status = classify_confirmation(state.get("current_utterance", ""))
        return {"confirmation_status": status}

    def execute_write_tool(self, state: ConversationState) -> dict[str, Any]:
        pending = state.get("pending_action") or {}
        intent = Intent(str(pending.get("intent")))
        args = dict(pending.get("arguments") or {})
        caller_id = UUID(str(state["caller_user_id"]))
        call_id = state.get("call_id", "local")
        idem = idempotency_key(call_id, intent.value, args.get("scheduled_for"), args.get("target_user_id"))
        try:
            if intent in {Intent.GENERAL_REMINDER_CREATE, Intent.SAFETY_REMINDER_CREATE}:
                reminder_type = (
                    ReminderType.HOUSEHOLD_SAFETY if intent == Intent.SAFETY_REMINDER_CREATE else ReminderType.GENERAL
                )
                result = self.tools.schedule_reminder(
                    ScheduleReminderInput(
                        requester_user_id=caller_id,
                        target_user_id=args["target_user_id"],
                        message=args["message"],
                        scheduled_for=args["scheduled_for"],
                        reminder_type=reminder_type,
                        reminder_subtype=args.get("subtype"),
                        recurrence_rule=args.get("recurrence_rule"),
                        source_call_id=call_id,
                        idempotency_key=idem,
                    )
                )
            elif intent == Intent.MEDICATION_PLAN_CREATE:
                local_time = args.get("local_time")
                if local_time is None:
                    raise ValidationError
                result = self.tools.create_medication_plan(
                    CreateMedicationPlanInput(
                        requester_user_id=caller_id,
                        target_user_id=args["target_user_id"],
                        medication_display_name=args["medication_name"],
                        schedule_rule=args.get("recurrence_rule") or "FREQ=DAILY",
                        local_schedule_time=local_time,
                        initial_inventory=args.get("initial_inventory"),
                        low_stock_threshold=self.settings.default_low_stock_threshold,
                        source_call_id=call_id,
                        idempotency_key=idem,
                    )
                )
            elif intent == Intent.APPOINTMENT_CREATE:
                result = self.tools.create_doctor_appointment(
                    CreateAppointmentInput(
                        requester_user_id=caller_id,
                        patient_user_id=args["target_user_id"],
                        provider_name=args.get("provider_name"),
                        scheduled_for=args["scheduled_for"],
                        source_call_id=call_id,
                        idempotency_key=idem,
                    )
                )
            else:
                raise ValidationError("write intent is not implemented in conversational MVP")
            return {
                "response_text": "Dogovoreno.",
                "pending_action": None,
                "confirmation_status": "confirmed",
                "tool_result": result.model_dump(mode="json"),
            }
        except DomainError as exc:
            return {
                "response_text": exc.user_message,
                "error_code": exc.code,
                "pending_action": None,
            }

    def execute_read_tool(self, state: ConversationState) -> dict[str, Any]:
        intent = Intent(state.get("intent") or Intent.UNKNOWN)
        args = state.get("extracted_arguments", {})
        requester = UUID(str(state["caller_user_id"]))
        target = args.get("target_user_id", requester)
        try:
            if intent == Intent.REMINDER_LIST:
                result = self.tools.list_upcoming_reminders(
                    ListRemindersInput(requester_user_id=requester, target_user_id=target)
                )
                items = cast(list[dict[str, object]], result.data.get("items", []))
                response = (
                    "Nemaš nadolazećih podsjetnika." if not items else f"Sljedeći podsjetnik je {items[0]['message']}."
                )
            elif intent == Intent.APPOINTMENT_QUERY:
                result = self.tools.get_next_doctor_appointment(
                    AppointmentQueryInput(requester_user_id=requester, patient_user_id=target)
                )
                if result.entity_id is None:
                    response = "Nema nadolazećih pregleda."
                else:
                    provider = result.data.get("provider_name") or "liječnika"
                    scheduled = datetime.fromisoformat(str(result.data["scheduled_for"]))
                    response = f"Sljedeći pregled je {format_local(scheduled)} kod {provider}."
            else:
                response = "Nisam pronašao traženi podatak."
                result = None
            return {
                "response_text": response,
                "tool_result": result.model_dump(mode="json") if result else None,
                "confirmation_status": "not_required",
            }
        except DomainError as exc:
            return {"response_text": exc.user_message, "error_code": exc.code}

    def cancel_pending_action(self, _state: ConversationState) -> dict[str, Any]:
        return {
            "response_text": "U redu, neću to napraviti.",
            "pending_action": None,
            "confirmation_status": "rejected",
        }

    def ask_confirmation_again(self, state: ConversationState) -> dict[str, Any]:
        pending = state.get("pending_action") or {}
        return {"response_text": f"Nisam razumio potvrdu. {pending.get('confirmation_text', '')}"}

    def apply_correction(self, state: ConversationState) -> dict[str, Any]:
        pending = dict(state.get("pending_action") or {})
        args = dict(pending.get("arguments") or {})
        try:
            now = datetime.fromisoformat(state["now_iso"])
            parsed = parse_croatian_time(
                state.get("current_utterance", ""), now=now, timezone=self.settings.default_timezone
            )
            args.update(
                scheduled_for=parsed.scheduled_for,
                recurrence_rule=parsed.recurrence_rule,
                local_time=parsed.local_time,
            )
            pending.update(arguments=args, stage="ready_for_confirmation")
            return {
                "pending_action": pending,
                "extracted_arguments": args,
                "confirmation_status": "correction_requested",
            }
        except ValidationError:
            pending.update(stage="clarifying", missing="scheduled_for", arguments=args)
            question = "Što želiš promijeniti? Reci mi točno vrijeme."
            return {
                "pending_action": pending,
                "clarification_question": question,
                "response_text": question,
            }

    def unsupported(self, _state: ConversationState) -> dict[str, Any]:
        return {
            "response_text": "Nisam to dobro razumio. Reci kratko što želiš da te podsjetim.",
            "pending_action": None,
        }

    @staticmethod
    def _missing_field(question: str) -> str:
        if "zove tableta" in question:
            return "medication_name"
        if "kojeg doktora" in question or "zove doktor" in question:
            return "provider_name"
        return "scheduled_for"

    def _resolve_target(self, utterance: str, caller_id: UUID) -> UUID:
        value = normalize_utterance(utterance)
        references = {
            "mamu": "Mama",
            "mama": "Mama",
            "tatu": "Tata",
            "tata": "Tata",
            "branka": "Branko",
            "branko": "Branko",
            "natašu": "Nataša",
            "nataša": "Nataša",
        }
        for phrase, name in references.items():
            if re.search(rf"\b{phrase}\b", value):
                return self.directory.by_name(name).id
        return caller_id

    @staticmethod
    def _reminder_message(utterance: str, subtype: str) -> str:
        defaults = {
            "tea": "da makneš čaj s plamenika",
            "oven": "da ugasiš pećnicu",
            "pot": "da makneš lonac",
            "stove": "da provjeriš štednjak",
            "iron": "da isključiš glačalo",
        }
        if subtype != "general":
            return defaults.get(subtype, "na ono što si tražio")
        tablet_match = re.search(
            r"\bda\s+((?:popije|pije|uzme|uzima)\s+(?:tabletu|lijek[\w-]*))",
            utterance,
            flags=re.IGNORECASE,
        )
        if tablet_match:
            return f"da {tablet_match.group(1).strip()}"
        da_match = re.search(
            r"\bda\s+(.+?)(?:\s+sutra|\s+prekosutra|\s+u\s+\d|\s+svaki|\s+svaku|\s+navečer|$)",
            utterance,
            flags=re.IGNORECASE,
        )
        if da_match:
            return f"da {da_match.group(1).strip(' .,' )}"
        return "na ono što si tražio"

    def _confirmation_text(self, intent: Intent, args: dict[str, Any], caller_id: UUID) -> str:
        target_phrase = self._target_phrase(args, caller_id)
        if intent == Intent.SAFETY_REMINDER_CREATE:
            return (
                f"U redu. Nazvat ću {target_phrase} {format_local(args['scheduled_for'])} "
                f"{args['message']}. Je li to točno?"
            )
        if intent == Intent.GENERAL_REMINDER_CREATE:
            message = args["message"]
            if message.startswith("da "):
                message = f"i reći joj {message}" if target_phrase != "tebe" else message
            return (
                f"U redu. Nazvat ću {target_phrase} {format_local(args['scheduled_for'])} "
                f"{message}. Je li to točno?"
            )
        if intent == Intent.MEDICATION_PLAN_CREATE:
            return medication_confirmation(
                args["medication_name"],
                args["local_time"].hour,
                target_phrase=target_phrase,
                inventory=args.get("initial_inventory"),
            )
        if intent == Intent.APPOINTMENT_CREATE:
            patient_phrase = target_phrase
            if patient_phrase == "tebe":
                return (
                    f"U redu. Imaš pregled kod {args['provider_name']} "
                    f"{format_local(args['scheduled_for'])}. Podsjetit ću te dan prije i dva sata prije. "
                    "Je li to točno?"
                )
            return (
                f"U redu. {args['provider_name'].title()} ima pregled "
                f"{format_local(args['scheduled_for'])}. Zvat ću {patient_phrase} dan prije i dva sata prije. "
                "Je li to točno?"
            )
        return "U redu. Je li to točno?"

    def _target_phrase(self, args: dict[str, Any], caller_id: UUID) -> str:
        target_id = args.get("target_user_id", caller_id)
        is_self = UUID(str(target_id)) == caller_id
        member = self.directory.by_id(UUID(str(target_id)))
        return target_call_phrase(member.display_name, is_self=is_self)

    @staticmethod
    def _parse_medication_name(utterance: str, normalized: str) -> str:
        if any(phrase in normalized for phrase in ("ne znam", "nije važno", "samo tableta")):
            return "tableta u dogovoreno vrijeme"
        name_match = re.search(
            r"(?:zove|naziva se|tableta je|lijek je)\s+([A-Za-zČĆĐŠŽčćđšž][\wČĆĐŠŽčćđšž-]+)",
            utterance,
            flags=re.IGNORECASE,
        )
        if name_match:
            return name_match.group(1)
        stripped = utterance.strip(" .")
        if stripped and " " not in stripped:
            return stripped
        return re.sub(r"^kod\s+", "", utterance, flags=re.IGNORECASE).strip(" .")
